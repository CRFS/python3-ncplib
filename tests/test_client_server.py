import asyncio
from datetime import datetime
from functools import partial
from ncplib import connect, start_server, CommandError, CommandWarning
from tests.base import AsyncTestCase


async def success_server_handler(client_disconnected_queue, client):
    async for field in client:
        field.send(ACKN=True)
        field.send(**field)
    # Allow testing.
    if client_disconnected_queue is not None:
        client_disconnected_queue.put_nowait(None)


async def error_server_handler(client_disconnected_queue, client):
    raise Exception("BOOM")


class ClientServerTestCase(AsyncTestCase):

    # Helpers.

    async def createServer(self, client_connected=success_server_handler, client_disconnected_queue=None, **kwargs):
        server = await start_server(
            partial(client_connected, client_disconnected_queue),
            "127.0.0.1", 0,
            loop=self.loop,
            **kwargs,
        )
        self.addCleanup(self.loop.run_until_complete, server.wait_closed())
        self.addCleanup(server.close)
        port = server.sockets[0].getsockname()[1]
        client = await connect("127.0.0.1", port, loop=self.loop)
        self.addCleanup(client.close)
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
        client = await self.createServer()
        self.assertIsInstance(client.transport, asyncio.WriteTransport)

    async def testSend(self):
        client = await self.createServer()
        response = client.send("PACK", "FIEL", FOO="BAR")
        await self.assertMessages(response, "PACK", {"FIEL": {"FOO": "BAR"}})

    async def testSendFiltersMessages(self):
        client = await self.createServer()
        # Send some junk.
        client.send("PACK", "FIEL", BAZ="QUX")
        # Send a field.
        response = client.send("PACK", "FIEL", FOO="BAR")
        await self.assertMessages(response, "PACK", {"FIEL": {"FOO": "BAR"}})

    async def testSendPacketData(self):
        client = await self.createServer()
        response = client.send_packet("PACK", FIEL={"FOO": "BAR"})
        await self.assertMessages(response, "PACK", {"FIEL": {"FOO": "BAR"}})

    async def testRecvFieldDataConnectionFiltersMessages(self):
        client = await self.createServer()
        client.send("PACK", "JUNK", BAZ="QUX")
        client.send("PACK", "FIEL", FOO="BAR")
        field = await client.recv_field("PACK", "FIEL")
        self.assertEqual(field, {"FOO": "BAR"})

    async def testRecvFieldDataResponseFiltersMessages(self):
        client = await self.createServer()
        client.send("PACK", "FIEL", BAZ="QUX")
        response = client.send("PACK", "FIEL", FOO="BAR")
        field = await response.recv_field("FIEL")
        self.assertEqual(field, {"FOO": "BAR"})

    async def testError(self):
        client = await self.createServer()
        client.send("PACK", "FIEL", ERRO="Boom!", ERRC=10)
        with self.assertRaises(CommandError) as cx:
            await client.recv()
        self.assertEqual(cx.exception.field.packet_type, "PACK")
        self.assertEqual(cx.exception.field.name, "FIEL")
        self.assertEqual(cx.exception.detail, "Boom!")
        self.assertEqual(cx.exception.code, 10)

    async def testWarning(self):
        client = await self.createServer()
        client.send("PACK", "FIEL", WARN="Boom!", WARC=10)
        with self.assertWarns(CommandWarning) as cx:
            await client.recv()
        self.assertEqual(cx.warning.field.packet_type, "PACK")
        self.assertEqual(cx.warning.field.name, "FIEL")
        self.assertEqual(cx.warning.detail, "Boom!")
        self.assertEqual(cx.warning.code, 10)

    async def testEncodeError(self):
        client = await self.createServer()
        client._writer.write(b"Boom!" * 1024)
        client._writer.write_eof()
        with self.assertLogs("ncplib.server", "WARN"):
            with self.assertRaises(CommandError) as cx:
                await client.recv()
        self.assertEqual(cx.exception.field.packet_type, "LINK")
        self.assertEqual(cx.exception.field.name, "ERRO")
        self.assertEqual(cx.exception.detail, "Bad request")
        self.assertEqual(cx.exception.code, 400)

    async def testServerError(self):
        with self.assertLogs("ncplib.server", "ERROR"):
            client = await self.createServer(error_server_handler)
            with self.assertRaises(CommandError) as cx:
                await client.recv()
        self.assertEqual(cx.exception.field.packet_type, "LINK")
        self.assertEqual(cx.exception.field.name, "ERRO")
        self.assertEqual(cx.exception.detail, "Server error")
        self.assertEqual(cx.exception.code, 500)

    async def testServerConnectionError(self):
        with self.assertLogs("ncplib.server", "ERROR"):
            with self.assertRaises(CommandError) as cx:
                await self.createServer(error_server_handler, auto_auth=False)
        self.assertEqual(cx.exception.field.packet_type, "LINK")
        self.assertEqual(cx.exception.field.name, "ERRO")
        self.assertEqual(cx.exception.detail, "Server error")
        self.assertEqual(cx.exception.code, 500)

    async def testConnectionWaitClosedDeprecated(self):
        client = await self.createServer()
        client.close()
        with self.assertWarns(DeprecationWarning):
            await client.wait_closed()

    async def testClientGracefulDisconnect(self):
        client_disconnected_queue = asyncio.Queue(loop=self.loop)
        client = await self.createServer(client_disconnected_queue=client_disconnected_queue)
        client.close()
        await client_disconnected_queue.get()
