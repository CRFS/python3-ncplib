import asyncio, logging, warnings
from datetime import datetime, timezone
from functools import partial
from operator import methodcaller, attrgetter
from uuid import getnode as get_mac

from ncplib.concurrent import sync, SyncWrapper
from ncplib.encoding import Field
from ncplib.errors import wrap_network_errors, ClientError, CommandError, CommandWarning
from ncplib.streams import write_packet, read_packet


__all__ = (
    "connect",
    "connect_sync",
)


logger = logging.getLogger(__name__)


PACKET_INFO = get_mac().to_bytes(6, "little", signed=False)[-4:]  # The last four bytes of the MAC address is used as an ID field.


# Known packet types.

PACKET_TYPE_LINK = b"LINK"

PACKET_TYPE_NODE = b"NODE"

PACKET_TYPE_DSP_CONTROL = b"DSPC"

PACKET_TYPE_DSP_LOOP = b"DSPL"

PACKET_TYPE_CRFS = b"CRFS"


# Known fields.

FIELD_HELLO = b"HELO"

FIELD_ACKNOWLEDGE_PACKET = b"ACKN"

FIELD_ERROR = b"ERRO"

FIELD_ERROR_CODE = b"ERRC"

FIELD_WARNING = b"WARN"

FIELD_WARNING_CODE = b"WARC"


class ClientLoggerAdapter(logging.LoggerAdapter):

    def process(self, msg, kwargs):
        msg, kwargs = super().process(msg, kwargs)
        return "ncp://{host}:{port} - {msg}".format(
            msg = msg,
            **self.extra
        ), kwargs


def run_with_packet_type(func, packet_type):
    @asyncio.coroutine
    def do_run_with_packet_type(self, fields):
        return (yield from func(self, packet_type, fields))
    return do_run_with_packet_type


def run_with_lock(func, lock_name):
    @asyncio.coroutine
    def do_run_with_lock(self, fields):
        with (yield from getattr(self, lock_name)):
            return (yield from func(self, fields))
    return do_run_with_lock


def run_single(func):
    @asyncio.coroutine
    def do_run_single(self, field, params=None):
        params = {} if params is None else params
        response_fields = yield from func(self, {field: params})
        return response_fields[field]
    return do_run_single


class Client:

    def __init__(self, host, port, *, loop=None):
        self._host = host
        self._port = port
        self._loop = loop or asyncio.get_event_loop()
        self._logger = ClientLoggerAdapter(logger, {
            "host": host,
            "port": port,
        })
        # Background reading.
        self._reader = None
        self._reader_coro = None
        # Writer multiplexing.
        self._id_gen = 0
        self._writer = None
        # Communication.
        self._waiters = {}
        # Locks.
        self._dspc_lock = asyncio.Lock(loop=self._loop)

    # Waiter handling.

    def _iter_active_waiters(self):
        return (
            future
            for future
            in self._waiters.values()
            if not future.cancelled()
        )

    def _wait_for_done(self, field_id, future):
        del self._waiters[field_id]

    def _wait_for_field(self, field):
        assert not field.id in self._waiters
        future = asyncio.Future(loop=self._loop)
        self._waiters[field.id] = future
        future.add_done_callback(partial(self._wait_for_done, field.id))
        return future

    # Connection lifecycle.

    @asyncio.coroutine
    def _connect(self):
        # Connect to the node.
        with wrap_network_errors():
            self._reader, self._writer = yield from asyncio.open_connection(self._host, self._port, loop=self._loop)
        self._logger.info("Connected")
        # Read the initial LINK HELO packet.
        helo_packet = yield from self._read_packet()
        if not (helo_packet.type == PACKET_TYPE_LINK and FIELD_HELLO in self._decode_fields(helo_packet.fields)):
            raise ClientError("Did not receive HELO packet")
        # Start up the background reader.
        self._reader_coro = asyncio.async(self._run_reader(), loop=self._loop)

    def close(self):
        # Shut down the background reader.
        self._reader_coro.cancel()
        # Shut down any waiters.
        for future in self._iter_active_waiters():
            future.cancel()
        # Shut down the stream.
        self._writer.close()
        self._logger.info("Cleanly disconnected")

    @asyncio.coroutine
    def wait_closed(self):
        waiting_tasks = list(self._iter_active_waiters())
        waiting_tasks.append(self._reader_coro)
        yield from asyncio.wait_for(waiting_tasks, loop=self._loop)

    # Packet reading.

    @asyncio.coroutine
    def _run_reader(self):
        while True:
            try:
                packet = yield from self._read_packet()
            except asyncio.CancelledError:
                raise
            except Exception as ex:
                # Propagate the exception to all waiters.
                for future in self._iter_active_waiters():
                    future.set_exception(ex)
            else:
                # Send the packet to all waiters.
                for field in packet.fields:
                    try:
                        future = self._waiters[field.id]
                    except KeyError:
                        pass
                    else:
                        if not future.cancelled():
                            # Handle acknowledgements.
                            if FIELD_ACKNOWLEDGE_PACKET in field.params:
                                self._logger.debug("Received ack %s", field.params[FIELD_ACKNOWLEDGE_PACKET])
                            elif FIELD_ERROR in field.params or FIELD_ERROR_CODE in field.params:
                                future.set_exception(CommandError(field.params.get(FIELD_ERROR), field.params.get(FIELD_ERROR_CODE), field.name))
                            elif FIELD_WARNING in field.params or FIELD_WARNING_CODE in field.params:
                                warnings.warn(CommandWarning(field.params.get(FIELD_WARNING), field.params.get(FIELD_WARNING_CODE), field.name))
                            else:
                                future.set_result(field)

    @asyncio.coroutine
    def _read_packet(self):
        packet = yield from read_packet(self._reader)
        self._logger.debug("Received packet %s %s", packet.type, packet.fields)
        return packet

    def _decode_fields(self, fields):
        return dict(map(attrgetter("name", "params"), fields))

    # Packet writing.

    def _gen_id(self):
        self._id_gen += 1
        return self._id_gen

    def _write_packet(self, packet_type, fields):
        write_packet(self._writer, packet_type, self._gen_id(), datetime.now(tz=timezone.utc), PACKET_INFO, fields)
        self._logger.debug("Sent packet %s %s", packet_type, fields)

    # Public API.

    @asyncio.coroutine
    def run_raw_multi(self, packet_type, fields):
        # Convert the fields to Field.
        fields = [
            Field(
                name = field_name,
                id = self._gen_id(),
                params = params,
            )
            for field_name, params
            in fields.items()
        ]
        # Sent the packet.
        self._write_packet(packet_type, fields)
        # Wait for all the fields.
        response_promises, _ = yield from asyncio.wait(map(self._wait_for_field, fields), loop=self._loop)
        # All done!
        return self._decode_fields(map(methodcaller("result"), response_promises))

    run_link_multi = run_with_packet_type(run_raw_multi, PACKET_TYPE_LINK)

    run_link = run_single(run_link_multi)

    run_node_multi = run_with_packet_type(run_raw_multi, PACKET_TYPE_NODE)

    run_node = run_single(run_node_multi)

    run_dsp_control_multi = run_with_lock(run_with_packet_type(run_raw_multi, PACKET_TYPE_DSP_CONTROL), "_dspc_lock")

    run_dsp_control = run_single(run_dsp_control_multi)


@asyncio.coroutine
def connect(host, port, *, loop=None):
    client = Client(host, port, loop=loop)
    yield from client._connect()
    return client


def connect_sync(host, port, *, loop=None, timeout=None):
    client = sync()(connect)(host, port, loop=loop, timeout=timeout)
    return SyncWrapper(client)
