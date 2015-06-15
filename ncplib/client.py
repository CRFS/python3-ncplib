import asyncio, logging
from datetime import datetime, timezone
from functools import partial
from operator import methodcaller
from uuid import getnode as get_mac

from ncplib.concurrent import sync, SyncWrapper
from ncplib.streams import write_packet, read_packet
from ncplib.encoding import Field


logger = logging.getLogger(__name__)


PACKET_INFO = get_mac().to_bytes(6, "little", signed=False)[-4:]  # The last four bytes of the MAC address is used as an ID field.


class ClientLoggerAdapter(logging.LoggerAdapter):

    def process(self, msg, kwargs):
        msg, kwargs = super().process(msg, kwargs)
        return "ncp://{host}:{port} - {msg}".format(
            msg = msg,
            **self.extra
        ), kwargs


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
        self._reader, self._writer = yield from asyncio.open_connection(self._host, self._port, loop=self._loop)
        self._logger.info("Connected")
        # Read the initial LINK HELO packet.
        yield from self._read_packet()
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
                            future.set_result(field)

    @asyncio.coroutine
    def _read_packet(self):
        packet = yield from read_packet(self._reader)
        self._logger.debug("Received packet %s %s", packet.type, packet.fields)
        return packet

    # Packet writing.

    def _gen_id(self):
        self._id_gen += 1
        return self._id_gen

    def _write_packet(self, packet_type, fields):
        write_packet(self._writer, packet_type, self._gen_id(), datetime.now(tz=timezone.utc), PACKET_INFO, fields)
        self._logger.debug("Sent packet %s %s", packet_type, fields)

    # Public API.

    @asyncio.coroutine
    def run_commands(self, packet_type, fields):
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
        return {
            response_field.name: response_field.params
            for response_field
            in map(methodcaller("result"), response_promises)
        }

    @asyncio.coroutine
    def run_command(self, packet_type, field, params=None):
        params = {} if params is None else params
        return (yield from self.run_commands(packet_type, {field: params}))


@asyncio.coroutine
def connect(host, port, *, loop=None):
    client = Client(host, port, loop=loop)
    yield from client._connect()
    return client


def connect_sync(host, port, *, loop=None, timeout=None):
    client = sync(loop=loop, timeout=timeout)(connect)(host, port, loop=loop)
    return SyncWrapper(client, loop=loop, timeout=timeout)
