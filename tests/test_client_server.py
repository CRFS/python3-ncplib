import asyncio
from datetime import datetime
from functools import partial
import sys
from ncplib import connect, start_server, CommandError, CommandWarning
from tests.base import AsyncTestCase


@asyncio.coroutine
def success_server_handler(client_disconnected_queue, client):
    assert client.remote_hostname == "ncplib-test"
    client_iter = client.__aiter__()
    try:
        while True:
            # Use the new async iteration protocol.
            if sys.version_info >= (3, 5):
                try:
                    field = yield from client_iter.__anext__()
                except StopAsyncIteration:
                    break
            else:
                # Use the old recv() protocol.
                try:
                    field = yield from client.recv()
                except EOFError:
                    break
            # Send a response.
            field.send(ACKN=True)
            field.send(**field)
    finally:
        # Allow testing.
        if client_disconnected_queue is not None:
            client_disconnected_queue.put_nowait(None)


@asyncio.coroutine
def error_server_handler(client_disconnected_queue, client):
    raise Exception("BOOM")


class ClientServerTestCase(AsyncTestCase):

    # Helpers.

    @asyncio.coroutine
    def createServer(
        self, client_connected=success_server_handler, *,
        client_disconnected_queue=None,
        server_auto_auth=True,
        client_auto_auth=True
    ):
        server = yield from start_server(
            partial(client_connected, client_disconnected_queue),
            "127.0.0.1", 0,
            loop=self.loop,
            auto_auth=server_auto_auth,
        )
        yield from server.__aenter__()
        self.addCleanup(self.loop.run_until_complete, server.__aexit__(None, None, None))
        port = server.sockets[0].getsockname()[1]
        client = yield from connect(
            "127.0.0.1", port,
            loop=self.loop,
            auto_auth=client_auto_auth,
            hostname="ncplib-test",
        )
        yield from client.__aenter__()
        self.addCleanup(self.loop.run_until_complete, client.__aexit__(None, None, None))
        return client

    @asyncio.coroutine
    def assertMessages(self, response, packet_type, expected_fields):
        fields = {}
        while len(fields) < len(expected_fields):
            field = yield from response.recv()
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

    @asyncio.coroutine
    def testClientTransport(self):
        client = yield from self.createServer()
        self.assertIsInstance(client.transport, asyncio.WriteTransport)

    @asyncio.coroutine
    def testSend(self):
        client = yield from self.createServer()
        response = client.send("PACK", "FIEL", FOO="BAR")
        yield from self.assertMessages(response, "PACK", {"FIEL": {"FOO": "BAR"}})

    @asyncio.coroutine
    def testSendFiltersMessages(self):
        client = yield from self.createServer()
        # Send some junk.
        client.send("PACK", "FIEL", BAZ="QUX")
        # Send a field.
        response = client.send("PACK", "FIEL", FOO="BAR")
        yield from self.assertMessages(response, "PACK", {"FIEL": {"FOO": "BAR"}})

    @asyncio.coroutine
    def testSendPacketData(self):
        client = yield from self.createServer()
        response = client.send_packet("PACK", FIEL={"FOO": "BAR"})
        yield from self.assertMessages(response, "PACK", {"FIEL": {"FOO": "BAR"}})

    @asyncio.coroutine
    def testRecvFieldDataConnectionFiltersMessages(self):
        client = yield from self.createServer()
        client.send("PACK", "JUNK", BAZ="QUX")
        client.send("PACK", "FIEL", FOO="BAR")
        field = yield from client.recv_field("PACK", "FIEL")
        self.assertEqual(field, {"FOO": "BAR"})

    @asyncio.coroutine
    def testRecvFieldDataResponseFiltersMessages(self):
        client = yield from self.createServer()
        client.send("PACK", "FIEL", BAZ="QUX")
        response = client.send("PACK", "FIEL", FOO="BAR")
        field = yield from response.recv_field("FIEL")
        self.assertEqual(field, {"FOO": "BAR"})

    @asyncio.coroutine
    def testError(self):
        client = yield from self.createServer()
        client.send("PACK", "FIEL", ERRO="Boom!", ERRC=10)
        with self.assertRaises(CommandError) as cx:
            yield from client.recv()
        self.assertEqual(cx.exception.field.packet_type, "PACK")
        self.assertEqual(cx.exception.field.name, "FIEL")
        self.assertEqual(cx.exception.detail, "Boom!")
        self.assertEqual(cx.exception.code, 10)

    @asyncio.coroutine
    def testWarning(self):
        client = yield from self.createServer()
        client.send("PACK", "FIEL", WARN="Boom!", WARC=10)
        with self.assertWarns(CommandWarning) as cx:
            yield from client.recv()
        self.assertEqual(cx.warning.field.packet_type, "PACK")
        self.assertEqual(cx.warning.field.name, "FIEL")
        self.assertEqual(cx.warning.detail, "Boom!")
        self.assertEqual(cx.warning.code, 10)

    @asyncio.coroutine
    def testAuthenticationError(self):
        client = yield from self.createServer(client_auto_auth=False)
        yield from client.recv_field("LINK", "HELO")
        client.send("LINK", "CCRE")
        with self.assertLogs("ncplib.server", "WARN"):
            with self.assertRaises(CommandError) as cx:
                yield from client.recv()
        self.assertEqual(cx.exception.field.packet_type, "LINK")
        self.assertEqual(cx.exception.field.name, "CCRE")
        self.assertEqual(cx.exception.detail, "CIW - This field is required")
        self.assertEqual(cx.exception.code, 401)

    @asyncio.coroutine
    def testEncodeError(self):
        client = yield from self.createServer()
        client._writer.write(b"Boom!" * 1024)
        client._writer.write_eof()
        with self.assertLogs("ncplib.server", "WARN"):
            with self.assertRaises(CommandError) as cx:
                yield from client.recv()
        self.assertEqual(cx.exception.field.packet_type, "LINK")
        self.assertEqual(cx.exception.field.name, "ERRO")
        self.assertEqual(cx.exception.detail, "Bad request")
        self.assertEqual(cx.exception.code, 400)

    @asyncio.coroutine
    def testServerError(self):
        with self.assertLogs("ncplib.server", "ERROR"):
            client = yield from self.createServer(error_server_handler)
            with self.assertRaises(CommandError) as cx:
                yield from client.recv()
        self.assertEqual(cx.exception.field.packet_type, "LINK")
        self.assertEqual(cx.exception.field.name, "ERRO")
        self.assertEqual(cx.exception.detail, "Server error")
        self.assertEqual(cx.exception.code, 500)

    @asyncio.coroutine
    def testServerConnectionError(self):
        with self.assertLogs("ncplib.server", "ERROR"):
            with self.assertRaises(CommandError) as cx:
                yield from self.createServer(error_server_handler, server_auto_auth=False)
        self.assertEqual(cx.exception.field.packet_type, "LINK")
        self.assertEqual(cx.exception.field.name, "ERRO")
        self.assertEqual(cx.exception.detail, "Server error")
        self.assertEqual(cx.exception.code, 500)

    @asyncio.coroutine
    def testClientGracefulDisconnect(self):
        client_disconnected_queue = asyncio.Queue(loop=self.loop)
        client = yield from self.createServer(client_disconnected_queue=client_disconnected_queue)
        yield from client.__aexit__(None, None, None)
        yield from client_disconnected_queue.get()
