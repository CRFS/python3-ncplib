import asyncio
import logging


logger = logging.getLogger(__name__)


class Request:

    def __init__(self, client_reader, client_writer):
        self._client_reader = client_reader
        self._client_writer = client_writer


class Server:

    def __init__(self, host, port, *, loop=None, **kwargs):
        self._host = host
        self._port = port
        self._loop = loop or asyncio.get_event_loop()
        # Logging.
        self.logger = logger

    async def _start(self):
        self._server = asyncio.start_server(self.__client_connected, self._host, self._port, loop=self._loop)

    async def _client_connected(self, client_reader, client_writer):
        pass
