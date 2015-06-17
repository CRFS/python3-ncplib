import asyncio, logging, warnings
from datetime import datetime, timezone
from itertools import filterfalse
from operator import methodcaller, attrgetter
from uuid import getnode as get_mac

from ncplib.concurrent import sync
from ncplib.encoding import Field
from ncplib.errors import wrap_network_errors, PacketError, PacketWarning
from ncplib.streams import write_packet, read_packet


__all__ = (
    "connect",
    "connect_sync",
)


logger = logging.getLogger(__name__)


CLIENT_ID = get_mac().to_bytes(6, "little", signed=False)[-4:]  # The last four bytes of the MAC address is used as an ID field.


class ClientLoggerAdapter(logging.LoggerAdapter):

    def process(self, msg, kwargs):
        msg, kwargs = super().process(msg, kwargs)
        return "ncp://{host}:{port} - {msg}".format(
            msg = msg,
            **self.extra
        ), kwargs


def decode_field_futures(field_futures):
    return dict(map(attrgetter("name", "params"), map(methodcaller("result"), field_futures)))


class ClientResponse:

    def __init__(self, client, packet_type, fields):
        self._client = client
        self._packet_type = packet_type
        self._fields = {
            field.name: field
            for field
            in fields
        }

    @asyncio.coroutine
    def _recv_field(self, field):
        return (yield from self._client.recv_field(self._packet_type, field.name, field.id))

    @asyncio.coroutine
    def recv(self):
        field_futures, _ = yield from asyncio.wait(map(self._recv_field, self._fields.values()), loop=self._client._loop)
        return decode_field_futures(field_futures)

    @asyncio.coroutine
    def recv_any(self):
        field_futures, field_futures_pending = yield from asyncio.wait(map(self._recv_field, self._fields.values()), return_when=asyncio.FIRST_COMPLETED, loop=self._client._loop)
        # Cancel the pending futures.
        for field_future in field_futures_pending:
            field_future.cancel()
        # Decode the futures we have.
        return decode_field_futures(field_futures)

    @asyncio.coroutine
    def recv_field(self, field_name):
        try:
            field = self._fields[field_name]
        except KeyError:
            raise ValueError("Response does not contain field {}".format(field_name))
        return (yield from self._recv_field(field)).params


class Client:

    def __init__(self, host, port, *, loop=None, auto_auth=True, auto_erro=True, auto_warn=True, auto_ackn=True, value_encoder=None, value_decoder=None):
        self._host = host
        self._port = port
        self._loop = loop or asyncio.get_event_loop()
        # Packet handling.
        self._auto_auth = auto_auth
        self._auto_erro = auto_erro
        self._auto_warn = auto_warn
        self._auto_ackn = auto_ackn
        self._value_encoder =  value_encoder
        self._value_decoder = value_decoder
        # Logging.
        self._logger = ClientLoggerAdapter(logger, {
            "host": host,
            "port": port,
        })
        # Packet reading.
        self._background_reader = None
        self._reader = None
        # Packet writing.
        self._id_gen = 0
        self._writer = None
        # Multiplexing.
        self._waiters = set()

    def _gen_id(self):
        self._id_gen += 1
        return self._id_gen

    def _active_waiters(self):
        return filterfalse(methodcaller("done"), self._waiters)

    # Connection lifecycle.

    @asyncio.coroutine
    def _handle_auth(self):
        # Read the initial LINK HELO packet.
        yield from self.recv_field(b"LINK", b"HELO")
        # Send the connection request.
        self.send(b"LINK", {
            b"CCRE": {
                b"CIW\x00": CLIENT_ID,
            },
        })
        # Read the connection response packet.
        yield from self.recv_field(b"LINK", b"SCAR")
        # Send the auth request packet.
        self.send(b"LINK", {
            b"CARE": {
                b"CAR\x00": CLIENT_ID,
            },
        })
        # Read the auth response packet.
        yield from self.recv_field(b"LINK", b"SCON")

    @asyncio.coroutine
    def _connect(self):
        # Connect to the node.
        with wrap_network_errors():
            self._reader, self._writer = yield from asyncio.open_connection(self._host, self._port, loop=self._loop)
        self._logger.info("Connected")
        # Spawn the background reader.
        self._background_reader = asyncio.async(self._run_reader(), loop=self._loop)
        # Auto-authenticate.
        if self._auto_auth:
            yield from self._handle_auth()

    def close(self):
        # Cancel the background reader.
        self._background_reader.cancel()
        # Cancel all active waiters.
        for waiter in self._active_waiters():
            waiter.cancel()
        # Shut down the stream.
        self._writer.close()
        self._logger.info("Closed")

    @asyncio.coroutine
    def wait_closed(self):
        active_futures = list(self._waiters)
        active_futures.append(self._background_reader)
        yield from asyncio.wait(active_futures, loop=self._loop)

    # The reader loop.

    @asyncio.coroutine
    def _run_reader(self):
        while True:
            try:
                packet = yield from read_packet(self._reader, value_decoder=self._value_decoder)
                self._logger.debug("Received packet %s %s", packet.type, packet.fields)
                # Send the packet to all waiters.
                for waiter in self._active_waiters():
                    waiter.set_result(packet)
            except asyncio.CancelledError:
                # Stop reading if we've been cancelled.
                raise
            except Exception as ex:
                # Propagate the exception to all waiters.
                for waiter in self._active_waiters():
                    waiter.set_exception(ex)

    # Sending packets.

    def send(self, packet_type, fields):
        # Encode the fields.
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
        write_packet(self._writer, packet_type, self._gen_id(), datetime.now(tz=timezone.utc), CLIENT_ID, fields, value_encoder=self._value_encoder)
        self._logger.debug("Sent packet %s %s", packet_type, fields)
        # Return a streaming response.
        return ClientResponse(self, packet_type, fields)

    # Receiving packets.

    @asyncio.coroutine
    def recv(self):
        waiter = asyncio.Future(loop=self._loop)
        self._waiters.add(waiter)
        try:
            return (yield from waiter)
        finally:
            self._waiters.remove(waiter)

    def _handle_erro(self, packet, field):
        error_message = field.params.get(b"ERRO", None)
        error_code = field.params.get(b"ERRC", None)
        if error_message is not None or error_code is not None:
            raise PacketError(packet.type, field.name, field.id, error_message, error_code)

    def _handle_warn(self, packet, field):
        warning_message = field.params.get(b"WARN", None)
        warning_code = field.params.get(b"WARC", None)
        if warning_message is not None or warning_code is not None:
            warnings.warn(PacketWarning(packet.type, field.name, field.id, warning_message, warning_code))
        # Ignore the rest of packet-level warnings.
        if field.name == b"WARN":
            return True

    def _handle_ackn(self, packet, field):
        ackn = field.params.get(b"ACKN", None)
        return ackn is not None

    @asyncio.coroutine
    def recv_field(self, packet_type, field_name, field_id=None):
        while True:
            packet = yield from self.recv()
            if packet.type == packet_type:
                for field in packet.fields:
                    if field_name == field.name and (field_id is None or field.id == field_id):
                        # Handle errors.
                        if self._auto_erro and self._handle_erro(packet, field):
                            continue
                        # Handle warnings.
                        if self._auto_warn and self._handle_warn(packet, field):
                            continue
                        # Handle acks.
                        if self._auto_ackn and self._handle_ackn(packet, field):
                            continue
                        # All done!
                        return field

    # Helpers.

    @asyncio.coroutine
    def communicate(self, packet_type, fields):
        return (yield from self.send(packet_type, fields).recv())

    @asyncio.coroutine
    def execute(self, packet_type, field_name, params=None):
        return (yield from self.communicate(packet_type, {field_name: params or {}}))[field_name]


@asyncio.coroutine
def connect(host, port, *, loop=None, **kwargs):
    client = Client(host, port, loop=loop, **kwargs)
    yield from client._connect()
    return client


connect_sync = sync(connect)
