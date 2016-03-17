import asyncio
import logging
from ncplib.connection import Connection


__all__ = (
    "Server",
)


logger = logging.getLogger(__name__)


class Server:

    def __init__(self, client_connected, host, port, *, loop=None, auto_auth=True):
        self._client_connected = client_connected
        self._host = host
        self._port = port
        self._loop = loop or asyncio.get_event_loop()
        self._server = None
        # Logging.
        self.logger = logger
        # Packet handling.
        self._auto_auth = auto_auth
        # Active handlers.
        self._handlers = set()

    @property
    def sockets(self):
        return self._server.sockets

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

    def _do_client_connected(self, reader, writer):
        handler = self._loop.create_task(self._handle_client_connected(reader, writer))
        self._handlers.add(handler)
        handler.add_done_callback(self._handlers.remove)

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.close()
        await self.wait_closed()

    async def start(self):
        self._server = await asyncio.start_server(
            self._do_client_connected,
            self._host,
            self._port,
            loop=self._loop,
        )
        self.logger.info("Started server on ncp://{host}:{port}".format(
            host=self._host,
            port=self._port,
        ))

    def close(self):
        # Cancel all the handlers.
        for handler in self._handlers:
            handler.cancel()
        # Close the server.
        self._server.close()
        self.logger.info("Closed server on ncp://{host}:{port}".format(
            host=self._host,
            port=self._port,
        ))

    async def wait_closed(self):
        await asyncio.gather(*self._handlers, self._server.wait_closed(), loop=self._loop, return_exceptions=True)
