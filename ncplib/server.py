import asyncio
import logging
from ncplib.connection import Connection


__all__ = (
    "start_server",
)


logger = logging.getLogger(__name__)


class Server:

    def __init__(self, client_connected, host, port, *, loop=None, auto_auth=True):
        self._client_connected = client_connected
        self._host = host
        self._port = port
        self._loop = loop or asyncio.get_event_loop()
        # Logging.
        self.logger = logger
        # Packet handling.
        self._auto_auth = auto_auth

    async def _handle_auth(self, connection):
        connection.send("LINK", "HELO")
        await connection.recv_field("LINK", "CCRE")
        connection.send("LINK", "SCAR")
        await connection.recv_field("LINK", "CARE")
        connection.send("LINK", "SCON")

    async def _do_client_connected(self, reader, writer):
        remote_host, remote_port = writer.get_extra_info("peername")
        connection = Connection(remote_host, remote_port, reader, writer, self.logger, loop=self._loop)
        # Handle auth.
        if self._auto_auth:
            await self._handle_auth(connection)
        # Delegate to handler.
        try:
            await self._client_connected(connection)
        finally:
            connection.close()
            await connection.wait_closed()

    async def _start(self):
        self._server = await asyncio.start_server(self._do_client_connected, self._host, self._port, loop=self._loop)
        self.logger.info("Started server on ncp://{host}:{port}".format(
            host=self._host,
            port=self._port,
        ))

    def close(self):
        self._server.close()
        self.logger.info("Closed server on ncp://{host}:{port}".format(
            host=self._host,
            port=self._port,
        ))

    async def wait_closed(self):
        await self._server.wait_closed()


async def start_server(client_connected, host, port, **kwargs):
    server = Server(client_connected, host, port, **kwargs)
    await server._start()
    return server