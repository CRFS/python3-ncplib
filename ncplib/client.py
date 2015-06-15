import asyncio, logging, warnings
from collections import defaultdict
from datetime import datetime, timezone
from functools import partial, wraps
from operator import methodcaller, attrgetter
from uuid import getnode as get_mac

from ncplib.concurrent import sync
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
    @wraps(func)
    def do_run_with_packet_type(self, fields):
        return (yield from func(self, packet_type, fields))
    return do_run_with_packet_type


def run_single(func):
    @asyncio.coroutine
    @wraps(func)
    def do_run_single(self, field, params=None):
        params = {} if params is None else params
        response_fields = yield from func(self, {field: params})
        return response_fields[field]
    return do_run_single


class StreamResponse:

    def __init__(self, client, packet_type, fields, lock):
        self._client = client
        self._packet_type = packet_type
        self._fields = fields
        self._lock = lock

    @asyncio.coroutine
    def read_all(self):
        return (yield from self._client._wait_for_all_fields(self._fields))

    def close(self):
        # Send a loop close packet.
        self._client._write_packet(self._packet_type, {})
        # Release the loop lock.
        self._lock.release()

    # Use as a context manager.

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


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
        self._packet_type_locks = defaultdict(partial(asyncio.Lock, loop=self._loop))

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

    @asyncio.coroutine
    def _wait_for_all_fields(self, fields):
        response_promises, _ = yield from asyncio.wait(map(self._wait_for_field, fields), loop=self._loop)
        return self._decode_fields(map(methodcaller("result"), response_promises))

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
        yield from asyncio.wait(waiting_tasks, loop=self._loop)

    # Use as a context manager.

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

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
                            params = field.params.copy()
                            # If there is an error, raise it.
                            if FIELD_ERROR in field.params or FIELD_ERROR_CODE in field.params:
                                future.set_exception(CommandError(field.params.pop(FIELD_ERROR, None), field.params.pop(FIELD_ERROR_CODE, None), field.name))
                            # If there is an ack, log it, but do nothing else.
                            elif FIELD_ACKNOWLEDGE_PACKET in params:
                                self._logger.debug("Received %s ack %s", field.name, params.pop(FIELD_ACKNOWLEDGE_PACKET, None))
                            else:
                                # If there is a warning, raise it, but continue.
                                if FIELD_WARNING in field.params or FIELD_WARNING_CODE in field.params:
                                    warnings.warn(CommandWarning(field.params.pop(FIELD_WARNING, None), field.params.pop(FIELD_WARNING_CODE, None), field.name))
                                # Set the result.
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

    def _encode_fields(self, fields):
        return [
            Field(
                name = field_name,
                id = self._gen_id(),
                params = params,
            )
            for field_name, params
            in fields.items()
        ]

    # Public API.

    @asyncio.coroutine
    def run_raw_multi(self, packet_type, fields):
        # Many of the packet types only allow a single command to be run at a time,
        # with subsequent commands cancelling previous ones. This lock ensures a single
        # command for a single packet type is run at a time.
        with (yield from self._packet_type_locks[packet_type]):
            # Convert the fields to Field.
            fields = self._encode_fields(fields)
            # Sent the packet.
            self._write_packet(packet_type, fields)
            # Wait for all the fields.
            return (yield from self._wait_for_all_fields(fields))

    @asyncio.coroutine
    def stream_raw_multi(self, packet_type, fields):
        # A loop can only run a single command at a time. This lock ensures that.
        lock = self._packet_type_locks[packet_type]
        yield from lock.acquire()
        # Convert the fields to Field.
        fields = self._encode_fields(fields)
        # Sent the packet.
        self._write_packet(packet_type, fields)
        # All done!
        return StreamResponse(self, packet_type, fields, lock)

    run_link_multi = run_with_packet_type(run_raw_multi, PACKET_TYPE_LINK)

    run_link = run_single(run_link_multi)

    run_node_multi = run_with_packet_type(run_raw_multi, PACKET_TYPE_NODE)

    run_node = run_single(run_node_multi)

    run_dsp_control_multi = run_with_packet_type(run_raw_multi, PACKET_TYPE_DSP_CONTROL)

    run_dsp_control = run_single(run_dsp_control_multi)

    stream_dsp_loop_multi = run_with_packet_type(stream_raw_multi, PACKET_TYPE_DSP_LOOP)


@asyncio.coroutine
def connect(host, port, *, loop=None):
    client = Client(host, port, loop=loop)
    yield from client._connect()
    return client


connect_sync = sync(connect)
