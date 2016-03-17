from datetime import datetime
from hypothesis import given, strategies as st
from ncplib import Client, Server, CommandError, CommandWarning
from ncplib.tests.base import AsyncTestCase
from ncplib.tests.strategies import names, params, ints, values


class ClientServerBaseTestCase(AsyncTestCase):

    async def serverHandler(self, client):
        async for message in client:
            message.send(ACKN=True)
            message.send(**message)

    def setUp(self):
        super().setUp()
        self.server = self.setupAsyncFixture(Server(self.serverHandler, "127.0.0.1", 0, loop=self.loop))
        port = self.server.sockets[0].getsockname()[1]
        self.client = self.setupAsyncFixture(Client("127.0.0.1", port, loop=self.loop))

    async def assertMessages(self, response, packet_type, expected_messages):
        messages = {}
        while len(messages) < len(expected_messages):
            message = await response.recv()
            messages[message.field_name] = message
            # Check the message structure.
            self.assertEqual(message.packet_type, packet_type)
            self.assertIsInstance(message.packet_timestamp, datetime)
            self.assertIn(message.field_name, expected_messages)
            self.assertIsInstance(message.field_id, int)
            self.assertEqual(len(message), len(expected_messages[message.field_name]))
        # Check the message content.
        assert messages == expected_messages


class ClientServerTestCase(ClientServerBaseTestCase):

    @given(names(), names(), params())
    async def testExecuteDeprecated(self, packet_type, field_name, params):
        with self.assertWarns(DeprecationWarning):
            message = await self.client.execute(packet_type, field_name, params)
        self.assertEqual(message, params)

    @given(names(), names(), params())
    async def testSend(self, packet_type, field_name, params):
        response = self.client.send(packet_type, field_name, **params)
        await self.assertMessages(response, packet_type, {field_name: params})

    @given(names(), names(), params(), params())
    async def testSendFiltersMessages(self, packet_type, field_name, params, junk_params):
        # Send some junk.
        self.client.send(packet_type, field_name, **junk_params)
        # Send a message.
        response = self.client.send(packet_type, field_name, **params)
        await self.assertMessages(response, packet_type, {field_name: params})

    @given(names(), st.dictionaries(names(), params()))
    async def testSendPacket(self, packet_type, fields):
        response = self.client.send_packet(packet_type, **fields)
        await self.assertMessages(response, packet_type, fields)

    @given(names(), st.dictionaries(names(), params()))
    async def testSendPacketDeprecated(self, packet_type, fields):
        with self.assertWarns(DeprecationWarning):
            response = self.client.send(packet_type, fields)
        await self.assertMessages(response, packet_type, fields)

    @given(names(), names(), params(), names())
    async def testRecvFieldConnectionFiltersMessages(self, packet_type, field_name, params, junk_field_name):
        self.client.send(packet_type, junk_field_name, **params)
        self.client.send(packet_type, field_name, **params)
        message = await self.client.recv_field(packet_type, field_name)
        self.assertEqual(message, params)

    @given(names(), names(), params(), params())
    async def testRecvFieldResponseFiltersMessages(self, packet_type, field_name, params, junk_params):
        self.client.send(packet_type, field_name, **junk_params)
        response = self.client.send(packet_type, field_name, **params)
        message = await response.recv_field(field_name)
        self.assertEqual(message, params)

    @given(names(), names(), values(), ints())
    async def testError(self, packet_type, field_name, detail, code):
        self.client.send(packet_type, field_name, ERRO=detail, ERRC=code)
        with self.assertLogs("ncplib.client", "ERROR"), self.assertRaises(CommandError) as cx:
            await self.client.recv()
        self.assertEqual(cx.exception.message.packet_type, packet_type)
        self.assertEqual(cx.exception.message.field_name, field_name)
        self.assertEqual(cx.exception.detail, detail)
        self.assertEqual(cx.exception.code, code)

    @given(names(), names(), values(), ints())
    async def testWarning(self, packet_type, field_name, detail, code):
        self.client.send(packet_type, field_name, WARN=detail, WARC=code)
        with self.assertLogs("ncplib.client", "WARN"), self.assertWarns(CommandWarning) as cx:
            await self.client.recv()
        self.assertEqual(cx.warning.message.packet_type, packet_type)
        self.assertEqual(cx.warning.message.field_name, field_name)
        self.assertEqual(cx.warning.detail, detail)
        self.assertEqual(cx.warning.code, code)


class ClientServerErrorTestCase(ClientServerBaseTestCase):

    async def serverHandler(self, client):
        await client.recv()
        raise Exception("BOOM")

    async def testServerError(self):
        with self.assertLogs("ncplib.client", "ERROR"), self.assertLogs("ncplib.server", "ERROR"):
            with self.assertRaises(CommandError) as cx:
                self.client.send("BOOM", "BOOM")
                await self.client.recv()
        self.assertEqual(cx.exception.message.packet_type, "LINK")
        self.assertEqual(cx.exception.message.field_name, "ERRO")
        self.assertEqual(cx.exception.detail, "Server error")
        self.assertEqual(cx.exception.code, 500)
