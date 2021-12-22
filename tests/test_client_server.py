from __future__ import annotations
import asyncio
from datetime import datetime
from functools import partial
from typing import Any, Awaitable, Callable, Mapping, MutableMapping
import ncplib
from ncplib.packets import Param
from ncplib.server import _create_server_connecton
from tests.base import AsyncTestCase


async def echo_server_handler(client: ncplib.Connection) -> None:
    assert client.remote_hostname == "ncplib-test"
    async for field in client:
        field.send(ACKN=True)
        field.send(**field)


async def error_server_handler(client: ncplib.Connection) -> None:
    raise Exception("BOOM")


async def disconnect_server_handler(client_disconnected_event: asyncio.Event, client: ncplib.Connection) -> None:
    try:
        async for field in client:
            field.send(ACKN=True)
            field.send(**field)
    finally:
        client_disconnected_event.set()


class ClientServerTestCase(AsyncTestCase):

    # Helpers.

    async def createServerRaw(
        self,
        client_connected: Callable[[asyncio.StreamReader, asyncio.StreamWriter], Awaitable[None]],
    ) -> int:
        server = await asyncio.start_server(
            client_connected,
            "127.0.0.1", 0,
        )
        self.addCleanup(self.loop.run_until_complete, server.__aexit__(None, None, None))
        return server.sockets[0].getsockname()[1]  # type: ignore

    async def createServer(
        self,
        client_connected: Callable[[ncplib.Connection], Awaitable[None]] = echo_server_handler,
    ) -> int:
        server = await ncplib.start_server(
            client_connected,
            "127.0.0.1", 0,
        )
        await server.__aenter__()
        self.addCleanup(self.loop.run_until_complete, server.__aexit__(None, None, None))
        return server.sockets[0].getsockname()[1]  # type: ignore

    async def _createClient(self, port: int, **kwargs: Any) -> ncplib.Connection:
        client = await ncplib.connect(
            "127.0.0.1", port,
            hostname="ncplib-test",
            **kwargs,
        )
        await client.__aenter__()
        self.addCleanup(self.loop.run_until_complete, client.__aexit__(None, None, None))
        return client

    async def createClientRaw(
        self,
        client_connected: Callable[[asyncio.StreamReader, asyncio.StreamWriter], Awaitable[None]],
        **kwargs: Any,
    ) -> ncplib.Connection:
        port = await self.createServerRaw(client_connected)
        return await self._createClient(port, **kwargs)

    async def createClient(
        self,
        client_connected: Callable[[ncplib.Connection], Awaitable[None]] = echo_server_handler,
        **kwargs: Any,
    ) -> ncplib.Connection:
        port = await self.createServer(client_connected)
        return await self._createClient(port, **kwargs)

    async def assertMessages(
        self, response: ncplib.Response, packet_type: str,
        expected_fields: Mapping[str, Mapping[str, Param]],
    ) -> None:
        fields: MutableMapping[str, Mapping[str, Param]] = {}
        while len(fields) < len(expected_fields):
            field = await response.recv()
            fields[field.name] = field
            # Check the field structure.
            self.assertEqual(field.packet_type, packet_type)
            self.assertIsInstance(field.packet_timestamp, datetime)
            self.assertIn(field.name, expected_fields)
            self.assertIsInstance(field.id, int)
            self.assertEqual(len(field), len(expected_fields[field.name]))
        # Check the field content.
        self.assertEqual(fields, expected_fields)

    # Tests.

    async def testClientTransport(self) -> None:
        client = await self.createClient()
        self.assertIsInstance(client.transport, asyncio.WriteTransport)

    async def testSend(self) -> None:
        client = await self.createClient()
        response = client.send("LINK", "ECHO", FOO="BAR")
        await self.assertMessages(response, "LINK", {"ECHO": {"FOO": "BAR"}})

    async def testSendFiltersMessages(self) -> None:
        client = await self.createClient()
        client.send("JUNK", "JUNK", JUNK="JUNK")
        client.send("LINK", "ECHO", BAZ="QUX")
        response = client.send("LINK", "ECHO", FOO="BAR")
        await self.assertMessages(response, "LINK", {"ECHO": {"FOO": "BAR"}})

    async def testSendPacket(self) -> None:
        client = await self.createClient()
        response = client.send_packet("LINK", ECHO={"FOO": "BAR"})
        await self.assertMessages(response, "LINK", {"ECHO": {"FOO": "BAR"}})

    async def testRecvFieldConnectionFiltersMessages(self) -> None:
        client = await self.createClient()
        client.send("JUNK", "JUNK", JUNK="JUNK")
        client.send("LINK", "ECHO", FOO="BAR")
        field = await client.recv_field("LINK", "ECHO")
        self.assertEqual(field, {"FOO": "BAR"})

    async def testRecvFieldResponseFiltersMessages(self) -> None:
        client = await self.createClient()
        client.send("LINK", "ECHO", BAZ="QUX")
        response = client.send("LINK", "ECHO", FOO="BAR")
        field = await response.recv_field("ECHO")
        self.assertEqual(field, {"FOO": "BAR"})

    async def testWarning(self) -> None:
        client = await self.createClient()
        response = client.send("LINK", "ECHO", WARN="Boom!", WARC=10)
        with self.assertWarns(ncplib.CommandWarning) as cx:
            await response.recv()
        self.assertEqual(cx.warning.field.packet_type, "LINK")  # type: ignore
        self.assertEqual(cx.warning.field.name, "ECHO")  # type: ignore
        self.assertEqual(cx.warning.detail, "Boom!")  # type: ignore
        self.assertEqual(cx.warning.code, 10)  # type: ignore

    async def testEncodeError(self) -> None:
        client = await self.createClient()
        client._writer.write(b"Boom!" * 1024)
        with self.assertLogs("ncplib.server", "WARN"):
            with self.assertRaises(ncplib.CommandError) as cx:
                while True:
                    await client.recv()
        self.assertEqual(cx.exception.field.packet_type, "LINK")
        self.assertEqual(cx.exception.field.name, "ERRO")
        self.assertEqual(cx.exception.detail, "Bad request")
        self.assertEqual(cx.exception.code, 400)

    async def testTopLevelServerError(self) -> None:
        with self.assertLogs("ncplib.server", "ERROR"):
            client = await self.createClient(error_server_handler)
            with self.assertRaises(ncplib.CommandError) as cx:
                await client.recv()
        self.assertEqual(cx.exception.field.packet_type, "LINK")
        self.assertEqual(cx.exception.field.name, "ERRO")
        self.assertEqual(cx.exception.detail, "Server error")
        self.assertEqual(cx.exception.code, 500)

    async def testServerConnectionError(self) -> None:
        async def client_connected(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            writer.close()
        with self.assertRaises(ncplib.ConnectionClosed):
            await self.createClientRaw(client_connected)

    async def testServerLegacyCcreLink(self) -> None:
        async def client_connected(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            async with _create_server_connecton(reader, writer, 60) as connection:
                connection.send("LINK", "HELO")
                await connection.recv_field("LINK", "CCRE")
                connection.send("LINK", "SCAR")
                await connection.recv_field("LINK", "CARE")
                connection.send("LINK", "SCON")
                connection._apply_remote_timeout(0)
                field = await connection.recv()
                field.send(ACKN=True)
                field.send(**field)
        client = await self.createClientRaw(client_connected)
        response = client.send("LINK", "ECHO", FOO="BAR")
        await self.assertMessages(response, "LINK", {"ECHO": {"FOO": "BAR"}})

    async def testServerInvalidCcreLink(self) -> None:
        async def client_connected(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            async with _create_server_connecton(reader, writer, 60) as connection:
                connection.send("LINK", "HELO")
                await connection.recv_field("LINK", "CCRE")
                connection.send("LINK", "SCAR", LINK="boom!")
                await connection.recv_field("LINK", "CARE")
                connection.send("LINK", "SCON")
                connection._apply_remote_timeout(0)
                field = await connection.recv()
                field.send(ACKN=True)
                field.send(**field)
        with self.assertWarns(ncplib.DecodeWarning) as cm:
            client = await self.createClientRaw(client_connected)
        self.assertEqual(str(cm.warning), "Invalid LINK SCAR LINK param: 'boom!'")
        response = client.send("LINK", "ECHO", FOO="BAR")
        await self.assertMessages(response, "LINK", {"ECHO": {"FOO": "BAR"}})

    async def testServerChangeCcreLink(self) -> None:
        with self.assertWarns(ncplib.NCPWarning) as cm:
            client = await self.createClient(timeout=9999)
        warnings = [str(w.message) for w in cm.warnings]
        self.assertIn("Changed connection timeout from 9999 to 60", warnings)
        self.assertIn("Server changed connection timeout to 60", warnings)
        self.assertEqual(client._timeout, 60)
        self.assertEqual(client._link_send_interval, 39)

    async def testClientGracefulDisconnect(self) -> None:
        client_disconnected_event = asyncio.Event()
        client = await self.createClient(partial(disconnect_server_handler, client_disconnected_event))
        # Ping a packet back and forth.
        response = client.send("LINK", "ECHO", FOO="bar")
        self.assertEqual((await response.recv())["FOO"], "bar")
        # Clost the client ahead of the server.
        await client.__aexit__(None, None, None)
        await client_disconnected_event.wait()
