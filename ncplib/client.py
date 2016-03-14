import asyncio
import logging
import warnings

from ncplib.connection import Connection
from ncplib.errors import CommandError, CommandWarning


__all__ = (
    "connect",
)


logger = logging.getLogger(__name__)


AUTH_ID = "python3-ncplib"


class ClientLoggerAdapter(logging.LoggerAdapter):

    def process(self, msg, kwargs):
        msg, kwargs = super().process(msg, kwargs)
        return "ncp://{host}:{port} - {msg}".format(
            msg=msg,
            **self.extra
        ), kwargs


class ClientResponse:

    def __init__(self, client, packet_type, field_lookup):
        self._client = client
        self._packet_type = packet_type
        self._fields_lookup = field_lookup

    async def recv_field(self, field_name):
        field_id = self._fields_lookup[field_name]
        return (await self._client.recv_field(self._packet_type, field_name, field_id=field_id))


class Client(Connection):

    def __init__(self, host, port, *, loop=None, auto_auth=True, auto_erro=True, auto_warn=True, auto_ackn=True):
        super().__init__(None, None, ClientLoggerAdapter(logger, {
            "host": host,
            "port": port,
        }), loop=loop)
        # Deferred connection.
        self._host = host
        self._port = port
        # Packet handling.
        self._auto_auth = auto_auth
        self._auto_erro = auto_erro
        self._auto_warn = auto_warn
        self._auto_ackn = auto_ackn

    # Connection lifecycle.

    async def _handle_auth(self):
        # Read the initial LINK HELO packet.
        await self.recv_field("LINK", "HELO")
        # Send the connection request.
        self.send("LINK", {
            "CCRE": {
                "CIW": AUTH_ID,
            },
        })
        # Read the connection response packet.
        await self.recv_field("LINK", "SCAR")
        # Send the auth request packet.
        self.send("LINK", {
            "CARE": {
                "CAR": AUTH_ID,
            },
        })
        # Read the auth response packet.
        await self.recv_field("LINK", "SCON")

    async def _connect(self):
        # Connect to the node.
        self._reader, self._writer = await asyncio.open_connection(self._host, self._port, loop=self._loop)
        self.logger.info("Connected")
        # Auto-authenticate.
        if self._auto_auth:
            await self._handle_auth()

    # Receiving fields.

    def _handle_erro(self, packet_type, field_name, params):
        error_message = params.get("ERRO", None)
        error_code = params.get("ERRC", None)
        if error_message is not None or error_code is not None:
            self.logger.error(
                "Command error in %s %s '%s' (code %s)",
                packet_type,
                field_name,
                error_message,
                error_code,
            )
            raise CommandError(packet_type, field_name, error_message, error_code)

    def _handle_warn(self, packet_type, field_name, params):
        warning_message = params.get("WARN", None)
        warning_code = params.get("WARC", None)
        if warning_message is not None or warning_code is not None:
            self.logger.warning(
                "Command warning in %s %s '%s' (code %s)",
                packet_type,
                field_name,
                warning_message,
                warning_code,
            )
            warnings.warn(CommandWarning(packet_type, field_name, warning_message, warning_code))
        # Ignore the rest of packet-level warnings.
        if field_name == "WARN":
            return True

    def _handle_ackn(self, packet_type, field_name, params):
        ackn = params.get("ACKN", None)
        return ackn is not None

    async def recv_field(self, packet_type, field_name, *, field_id=None):
        while True:
            params = await super().recv_field(packet_type, field_name, field_id=field_id)
            # Handle errors.
            if self._auto_erro and self._handle_erro(packet_type, field_name, params):
                continue
            # Handle warnings.
            if self._auto_warn and self._handle_warn(packet_type, field_name, params):
                continue
            # Handle acks.
            if self._auto_ackn and self._handle_ackn(packet_type, field_name, params):
                continue
            # All done!
            return params

    # Sending packets.

    def send(self, packet_type, fields):
        super().send(packet_type, fields)
        return ClientResponse(self, packet_type, {
            field.name: field.id
            for field
            in fields
        })

    async def execute(self, packet_type, field_name, params=None):
        return (await self.send(packet_type, {field_name: params or {}}).recv_field(field_name))


async def connect(host, port, **kwargs):
    client = Client(host, port, **kwargs)
    await client._connect()
    return client
