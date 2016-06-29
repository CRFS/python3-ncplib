import asyncio
from datetime import datetime
from ncplib import connect, start_server, CommandError, CommandWarning
from tests.base import AsyncTestCase


class ClientServerBaseTestCase(AsyncTestCase):

    async def serverHandler(self, client):
        async for field in client:
            field.send(ACKN=True)
            field.send(**field)

    def setUp(self):
        super().setUp()
        # Create a server handler.
        self.server = self.setupAsyncFixture(start_server(self.serverHandler, "127.0.0.1", 0, loop=self.loop))
        # Create a client.
        port = self.server.sockets[0].getsockname()[1]
        self.client = self.setupAsyncFixture(connect("127.0.0.1", port, loop=self.loop))

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


class ClientServerTestCase(ClientServerBaseTestCase):

    def testClientTransport(self):
        self.assertIsInstance(self.client.transport, asyncio.WriteTransport)

    async def testSend(self):
        response = self.client.send("PACK", "FIEL", FOO="BAR")
        await self.assertMessages(response, "PACK", {"FIEL": {"FOO": "BAR"}})

    async def testSendFiltersMessages(self):
        # Send some junk.
        self.client.send("PACK", "FIEL", BAZ="QUX")
        # Send a field.
        response = self.client.send("PACK", "FIEL", FOO="BAR")
        await self.assertMessages(response, "PACK", {"FIEL": {"FOO": "BAR"}})

    async def testSendPacketData(self):
        response = self.client.send_packet("PACK", FIEL={"FOO": "BAR"})
        await self.assertMessages(response, "PACK", {"FIEL": {"FOO": "BAR"}})

    async def testRecvFieldDataConnectionFiltersMessages(self):
        self.client.send("PACK", "JUNK", BAZ="QUX")
        self.client.send("PACK", "FIEL", FOO="BAR")
        field = await self.client.recv_field("PACK", "FIEL")
        self.assertEqual(field, {"FOO": "BAR"})

    async def testRecvFieldDataResponseFiltersMessages(self):
        self.client.send("PACK", "FIEL", BAZ="QUX")
        response = self.client.send("PACK", "FIEL", FOO="BAR")
        field = await response.recv_field("FIEL")
        self.assertEqual(field, {"FOO": "BAR"})

    async def testError(self):
        self.client.send("PACK", "FIEL", ERRO="Boom!", ERRC=10)
        with self.assertLogs("ncplib.client", "ERROR"), self.assertRaises(CommandError) as cx:
            await self.client.recv()
        self.assertEqual(cx.exception.field.packet_type, "PACK")
        self.assertEqual(cx.exception.field.name, "FIEL")
        self.assertEqual(cx.exception.detail, "Boom!")
        self.assertEqual(cx.exception.code, 10)

    async def testWarning(self):
        self.client.send("PACK", "FIEL", WARN="Boom!", WARC=10)
        with self.assertLogs("ncplib.client", "WARN"), self.assertWarns(CommandWarning) as cx:
            await self.client.recv()
        self.assertEqual(cx.warning.field.packet_type, "PACK")
        self.assertEqual(cx.warning.field.name, "FIEL")
        self.assertEqual(cx.warning.detail, "Boom!")
        self.assertEqual(cx.warning.code, 10)

    async def testEncodeError(self):
        self.client._writer.write(b"Boom!" * 1024)
        self.client._writer.write_eof()
        with self.assertLogs("ncplib.server", "WARN"):
            with self.assertLogs("ncplib.client", "WARN"), self.assertRaises(CommandError) as cx:
                await self.client.recv()
        self.assertEqual(cx.exception.field.packet_type, "LINK")
        self.assertEqual(cx.exception.field.name, "ERRO")
        self.assertEqual(cx.exception.detail, "Bad request")
        self.assertEqual(cx.exception.code, 400)


class ClientServerErrorTestCase(ClientServerBaseTestCase):

    async def serverHandler(self, client):
        await client.recv()
        raise Exception("BOOM")

    async def testServerError(self):
        with self.assertLogs("ncplib.client", "ERROR"), self.assertLogs("ncplib.server", "ERROR"):
            with self.assertRaises(CommandError) as cx:
                self.client.send("BOOM", "BOOM")
                await self.client.recv()
        self.assertEqual(cx.exception.field.packet_type, "LINK")
        self.assertEqual(cx.exception.field.name, "ERRO")
        self.assertEqual(cx.exception.detail, "Server error")
        self.assertEqual(cx.exception.code, 500)
