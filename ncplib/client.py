import asyncio, logging, warnings
from datetime import datetime, timezone
from functools import partial
from itertools import chain
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


class ClientLoggerAdapter(logging.LoggerAdapter):

    def process(self, msg, kwargs):
        msg, kwargs = super().process(msg, kwargs)
        return "ncp://{host}:{port} - {msg}".format(
            msg = msg,
            **self.extra
        ), kwargs


def decode_fields(fields):
    return dict(map(attrgetter("name", "params"), fields))


def decode_field_futures(field_futures):
    return decode_fields(map(methodcaller("result"), field_futures))


class ClientResponse:

    def __init__(self, client, fields):
        self._client = client
        self._fields = fields

    @asyncio.coroutine
    def read_all(self):
        field_futures, _ = yield from asyncio.wait(map(self._client._wait_for_field, self._fields.values()), loop=self._client._loop)
        return decode_field_futures(field_futures)

    @asyncio.coroutine
    def read_any(self):
        field_futures, field_futures_pending = yield from asyncio.wait(map(self._client._wait_for_field, self._fields.values()), return_when=asyncio.FIRST_COMPLETED, loop=self._client._loop)
        # Cancel the pending futures.
        for field_future in field_futures_pending:
            field_future.cancel()
        # Decode the futures we have.
        return decode_field_futures(field_futures)

    @asyncio.coroutine
    def read_field(self, field):
        try:
            field = self._fields[field]
        except KeyError:
            raise ValueError("Response does not contain field {}".format(field))
        return (yield from self._client._wait_for_field(field)).params


class Client:

    def __init__(self, host, port, *, loop=None, auto_ackn=True, auto_warn=True, auto_erro=True):
        self._host = host
        self._port = port
        self._loop = loop or asyncio.get_event_loop()
        # Packet handling.
        self._auto_ackn = auto_ackn
        self._auto_warn = auto_warn
        self._auto_erro = auto_erro
        # Logging.
        self._logger = ClientLoggerAdapter(logger, {
            "host": host,
            "port": port,
        })
        # Packet reading.
        self._reader = None
        # Packet writing.
        self._id_gen = 0
        self._writer = None
        # Multiplexing.
        self._tasks = set()
        self._waiters = {}

    # Task spawning.

    def _spawn(self, coro=None):
        coro = asyncio.Future(loop=self._loop) if coro is None else coro
        task = asyncio.async(coro, loop=self._loop)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.remove)
        return task

    # Waiter handling.

    def _wait_for_field_done(self, field_id, future):
        # Clean up the field waiters.
        field_waiters = self._waiters[field_id]
        field_waiters.remove(future)
        # Clean up the waiter dict, if we're out of waiters.
        if not field_waiters:
            del self._waiters[field_id]

    def _wait_for_field(self, field):
        # Spawn a background reader, if this is the first waiter.
        if not self._waiters:
            self._spawn(self._run_reader())
        # Get the field waiters.
        try:
            field_waiters = self._waiters[field.id]
        except KeyError:
            field_waiters = set()
            self._waiters[field.id] = field_waiters
        # Spawn a waiter.
        waiter = self._spawn()
        field_waiters.add(waiter)
        waiter.add_done_callback(partial(self._wait_for_field_done, field.id))
        # All done!
        return waiter

    # Packet reading.

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

    # Connection lifecycle.

    @asyncio.coroutine
    def _connect(self):
        # Connect to the node.
        with wrap_network_errors():
            self._reader, self._writer = yield from asyncio.open_connection(self._host, self._port, loop=self._loop)
        self._logger.info("Connected")
        # Read the initial LINK HELO packet.
        helo_packet = yield from self._read_packet()
        if not (helo_packet.type == b"LINK" and b"HELO" in decode_fields(helo_packet.fields)):
            raise ClientError("Did not receive LINK HELO packet")

    def close(self):
        # Cancel all tasks.
        for task in self._tasks:
            task.cancel()
        # Shut down the stream.
        self._writer.close()
        self._logger.info("Closed")

    @asyncio.coroutine
    def wait_closed(self):
        if self._tasks:
            yield from asyncio.wait(self._tasks, loop=self._loop)

    # The reader loop.

    @asyncio.coroutine
    def _run_reader(self):
        self._logger.debug("Starting background reader")
        try:
            while self._waiters:
                packet = yield from self._read_packet()
                # Send the packet to all waiters.
                for field in packet.fields:
                    try:
                        # Handle errors.
                        if self._auto_erro:
                            error_message = field.params.pop(b"ERRO", None)
                            error_code = field.params.pop(b"ERRC", None)
                            if error_message is not None or error_code is not None:
                                raise CommandError(error_message, error_code, field)
                        # Handle warnings.
                        if self._auto_warn:
                            warning_message = field.params.pop(b"WARN", None)
                            warning_code = field.params.pop(b"WARC", None)
                            if warning_message is not None or warning_code is not None:
                                warnings.warn(CommandWarning(warning_message, warning_code, field))
                        # Handle acks.
                        if self._auto_ackn:
                            ackn = field.params.pop(b"ACKN", None)
                            if ackn is not None:
                                continue  # Ignore the rest of the field for this waiter.
                        # Give the params to the waiter.
                        for future in self._waiters.get(field.id, ()):
                            if not future.cancelled():
                                future.set_result(field)
                    except Exception as ex:
                        # Send the exception to the waiter. We catch exceptions rather
                        # than calling set_exception directly in the error handler, since
                        # warnings might be configured to raise exceptions.
                        for future in self._waiters.get(field.id, ()):
                            if not future.cancelled():
                                future.set_exception(ex)
        except asyncio.CancelledError:
            # Stop reading if we've been cancelled.
            pass
        except Exception as ex:
            # Propagate the exception to all waiters.
            for future in chain.from_iterable(self._waiters.values()):
                if not future.cancelled():
                    future.set_exception(ex)
        finally:
            self._logger.debug("Shutting down background reader")

    # Public API.

    def send(self, packet_type, fields):
        # Encode the fields.
        fields = {
            field_name: Field(
                name = field_name,
                id = self._gen_id(),
                params = params,
            )
            for field_name, params
            in fields.items()
        }
        # Sent the packet.
        self._write_packet(packet_type, fields.values())
        # Return a streaming response.
        return ClientResponse(self, fields)

    @asyncio.coroutine
    def communicate(self, packet_type, fields):
        return (yield from self.send(packet_type, fields).read_all())


@asyncio.coroutine
def connect(host, port, *, loop=None):
    client = Client(host, port, loop=loop)
    yield from client._connect()
    return client


connect_sync = sync(connect)
