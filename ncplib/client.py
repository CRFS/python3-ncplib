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


class ClientConnection(Connection):

    def __init__(self, host, port, *, loop=None, auto_auth=True, auto_erro=True, auto_warn=True, auto_ackn=True):
        super().__init__(host, port, None, None, logger, loop=loop)
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
                self._packet_type,
                field_name,
                error_message,
                error_code,
            )
            raise CommandError(packet_type, field_name, error_message, error_code)
        return True

    def _handle_warn(self, packet_type, field_name, params):
        warning_message = params.get("WARN", None)
        warning_code = params.get("WARC", None)
        if warning_message is not None or warning_code is not None:
            self.logger.warning(
                "Command warning in %s %s '%s' (code %s)",
                self._packet_type,
                field_name,
                warning_message,
                warning_code,
            )
            warnings.warn(CommandWarning(packet_type, field_name, warning_message, warning_code))
        # Ignore the rest of packet-level warnings.
        return field_name != "WARN"

    def _handle_ackn(self, params):
        return "ACKN" not in params

    def _params_predicate(self, params):
        return (
            # Handle errors.
            (self._auto_erro and self._handle_erro(params)) or
            # Handle warnings.
            (self._auto_warn and self._handle_warn(params)) or
            # Handle acks.
            (self._auto_ackn and self._handle_ackn(params)) or
            # Otherwise, the field is unhandled.
            True
        )

    # Sending fields.

    def execute(self, *args, **kwargs):
        # TODO: Deprecate?
        return self.send(*args, **kwargs).get()


async def connect(host, port, **kwargs):
    client = ClientConnection(host, port, **kwargs)
    await client._connect()
    return client
