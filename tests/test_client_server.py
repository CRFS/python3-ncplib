import asyncio
from datetime import datetime
from functools import partial
import ncplib
from tests.base import AsyncTestCase


async def echo_server_handler(client):
    assert client.remote_hostname == "ncplib-test"
    async for field in client:
        field.send(ACKN=True)
        field.send(**field)


async def error_server_handler(client):
    raise Exception("BOOM")


async def disconnect_server_handler(client_disconnected_event, client):
    try:
        async for field in client:
            field.send(ACKN=True)
            field.send(**field)
    finally:
        client_disconnected_event.set()


class ClientServerTestCase(AsyncTestCase):

    # Helpers.

    async def createServer(self, client_connected=echo_server_handler, *, server_auto_auth=True):
        server = await ncplib.start_server(
            client_connected,
            "127.0.0.1", 0,
            auto_auth=server_auto_auth,
        )
        await server.__aenter__()
        self.addCleanup(self.loop.run_until_complete, server.__aexit__(None, None, None))
        return server.sockets[0].getsockname()[1]

    async def createClient(self, *args, client_auto_link=True, client_auto_auth=True, **kwargs):
        port = await self.createServer(*args, **kwargs)
        client = await ncplib.connect(
            "127.0.0.1", port,
            auto_link=client_auto_link,
            auto_auth=client_auto_auth,
            hostname="ncplib-test",
        )
        await client.__aenter__()
        self.addCleanup(self.loop.run_until_complete, client.__aexit__(None, None, None))
        return client

    async def assertMessages(self, response, packet_type, expected_fields):
        fields = {}
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

    async def testClientTransport(self):
        client = await self.createClient()
        self.assertIsInstance(client.transport, asyncio.WriteTransport)

    async def testSend(self):
        client = await self.createClient()
        response = client.send("LINK", "ECHO", FOO="BAR")
        await self.assertMessages(response, "LINK", {"ECHO": {"FOO": "BAR"}})

    async def testSendFiltersMessages(self):
        client = await self.createClient()
        client.send("JUNK", "JUNK", JUNK="JUNK")
        client.send("LINK", "ECHO", BAZ="QUX")
        response = client.send("LINK", "ECHO", FOO="BAR")
        await self.assertMessages(response, "LINK", {"ECHO": {"FOO": "BAR"}})

    async def testSendPacket(self):
        client = await self.createClient()
        response = client.send_packet("LINK", ECHO={"FOO": "BAR"})
        await self.assertMessages(response, "LINK", {"ECHO": {"FOO": "BAR"}})

    async def testRecvFieldConnectionFiltersMessages(self):
        client = await self.createClient()
        client.send("JUNK", "JUNK", JUNK="JUNK")
        client.send("LINK", "ECHO", FOO="BAR")
        field = await client.recv_field("LINK", "ECHO")
        self.assertEqual(field, {"FOO": "BAR"})

    async def testRecvFieldResponseFiltersMessages(self):
        client = await self.createClient()
        client.send("LINK", "ECHO", BAZ="QUX")
        response = client.send("LINK", "ECHO", FOO="BAR")
        field = await response.recv_field("ECHO")
        self.assertEqual(field, {"FOO": "BAR"})

    async def testWarning(self):
        client = await self.createClient()
        response = client.send("LINK", "ECHO", WARN="Boom!", WARC=10)
        with self.assertWarns(ncplib.CommandWarning) as cx:
            await response.recv()
        self.assertEqual(cx.warning.field.packet_type, "LINK")
        self.assertEqual(cx.warning.field.name, "ECHO")
        self.assertEqual(cx.warning.detail, "Boom!")
        self.assertEqual(cx.warning.code, 10)

    async def testAuthenticationError(self):
        client = await self.createClient(client_auto_auth=False)
        await client.recv_field("LINK", "HELO")
        client.send("LINK", "CCRE")
        with self.assertLogs("ncplib.server", "WARN"):
            with self.assertRaises(ncplib.CommandError) as cx:
                await client.recv()
        self.assertEqual(cx.exception.field.packet_type, "LINK")
        self.assertEqual(cx.exception.field.name, "CCRE")
        self.assertEqual(cx.exception.detail, "CIW - This field is required")
        self.assertEqual(cx.exception.code, 401)

    async def testEncodeError(self):
        client = await self.createClient(client_auto_link=False)
        client._writer.write(b"Boom!" * 1024)
        client._writer.write_eof()
        with self.assertLogs("ncplib.server", "WARN"):
            with self.assertRaises(ncplib.CommandError) as cx:
                while True:
                    await client.recv()
        self.assertEqual(cx.exception.field.packet_type, "LINK")
        self.assertEqual(cx.exception.field.name, "ERRO")
        self.assertEqual(cx.exception.detail, "Bad request")
        self.assertEqual(cx.exception.code, 400)

    async def testTopLevelServerError(self):
        with self.assertLogs("ncplib.server", "ERROR"):
            client = await self.createClient(error_server_handler)
            with self.assertRaises(ncplib.CommandError) as cx:
                await client.recv()
        self.assertEqual(cx.exception.field.packet_type, "LINK")
        self.assertEqual(cx.exception.field.name, "ERRO")
        self.assertEqual(cx.exception.detail, "Server error")
        self.assertEqual(cx.exception.code, 500)

    async def testServerConnectionError(self):
        with self.assertLogs("ncplib.server", "ERROR"):
            with self.assertRaises(ncplib.CommandError) as cx:
                await self.createClient(error_server_handler, server_auto_auth=False)
        self.assertEqual(cx.exception.field.packet_type, "LINK")
        self.assertEqual(cx.exception.field.name, "ERRO")
        self.assertEqual(cx.exception.detail, "Server error")
        self.assertEqual(cx.exception.code, 500)

    async def testClientGracefulDisconnect(self):
        client_disconnected_event = asyncio.Event()
        client = await self.createClient(partial(disconnect_server_handler, client_disconnected_event))
        # Ping a packet back and forth.
        response = client.send("LINK", "ECHO", FOO="bar")
        self.assertEqual((await response.recv())["FOO"], "bar")
        # Clost the client ahead of the server.
        await client.__aexit__(None, None, None)
        await client_disconnected_event.wait()
