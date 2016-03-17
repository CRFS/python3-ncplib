import asyncio
import logging
from ncplib.connection import Connection, ClosableContextMixin


__all__ = (
    "ServerHandler",
)


logger = logging.getLogger(__name__)


class ServerHandler(ClosableContextMixin):

    def __init__(self, client_connected, *, loop=None, auto_auth=True):
        self._client_connected = client_connected
        self._loop = loop or asyncio.get_event_loop()
        # Logging.
        self.logger = logger
        # Packet handling.
        self._auto_auth = auto_auth
        # Active handlers.
        self._handlers = set()

    async def _handle_auth(self, connection):
        connection.send("LINK", "HELO")
        await connection.recv_field("LINK", "CCRE")
        connection.send("LINK", "SCAR")
        await connection.recv_field("LINK", "CARE")
        connection.send("LINK", "SCON")

    async def _handle_client_connected(self, reader, writer):
        remote_host, remote_port = writer.get_extra_info("peername")
        async with Connection(remote_host, remote_port, reader, writer, self.logger, loop=self._loop) as client:
            try:
                # Handle auth.
                if self._auto_auth:
                    await self._handle_auth(client)
                # Delegate to handler.
                await self._client_connected(client)
            except asyncio.CancelledError:  # pragma: no cover
                pass
            except:
                logger.exception("Unexpected error")
                client.send("LINK", "ERRO", ERRO="Server error", ERRC=500)

    def __call__(self, reader, writer):
        handler = self._loop.create_task(self._handle_client_connected(reader, writer))
        self._handlers.add(handler)
        handler.add_done_callback(self._handlers.remove)

    def close(self):
        for handler in self._handlers:
            handler.cancel()

    async def wait_closed(self):
        if self._handlers:
            await asyncio.gather(*self._handlers, loop=self._loop, return_exceptions=True)
