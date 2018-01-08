import asyncio
from datetime import datetime
from functools import partial
import sys
import ncplib
from tests.base import AsyncTestCase


class EchoApplication(ncplib.Application):

    @asyncio.coroutine
    def handle_unknown_field(self, field):
        yield from super().handle_unknown_field(field)
        assert self.connection.remote_hostname == "ncplib-test"
        field.send(ACKN=True)
        field.send(**field)

    @asyncio.coroutine
    def handle_field_LINK_BAD(self, field):
        raise ncplib.BadRequest("Boom!")

    @asyncio.coroutine
    def handle_field_LINK_BOOM(self, field):
        raise Exception("Boom!")


@asyncio.coroutine
def error_server_handler(client):
    raise Exception("BOOM")


@asyncio.coroutine
def decode_error_server_handler(client):
    client._writer.write(b"Boom!" * 1024)
    client._writer.write_eof()


@asyncio.coroutine
def disconnect_server_handler(client_disconnected_event, client):
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
                except ncplib.ConnectionClosed:
                    break
            # Send a response.
            field.send(ACKN=True)
            field.send(**field)
    finally:
        client_disconnected_event.set()


class ClientApplication(ncplib.Application):

    def __init__(self, connection, **spam_data):
        super().__init__(connection)
        self._spam_data = spam_data

    @asyncio.coroutine
    def run_spam(self):
        for _ in range(3):
            self.connection.send("SPAM", "SPAM", **self._spam_data)
            yield from asyncio.sleep(0.1, loop=self.connection._loop)
        self.connection.close()

    @asyncio.coroutine
    def handle_connect(self):
        yield from super().handle_connect()
        self.start_daemon(self.run_spam())


class ClientServerTestCase(AsyncTestCase):

    # Helpers.

    @asyncio.coroutine
    def createServer(self, client_connected=EchoApplication, *, server_auto_auth=True):
        server = yield from ncplib.start_server(
            client_connected,
            "127.0.0.1", 0,
            loop=self.loop,
            auto_auth=server_auto_auth,
        )
        yield from server.__aenter__()
        self.addCleanup(self.loop.run_until_complete, server.__aexit__(None, None, None))
        return server.sockets[0].getsockname()[1]

    @asyncio.coroutine
    def createClient(self, *args, client_auto_link=True, client_auto_auth=True, **kwargs):
        port = yield from self.createServer(*args, **kwargs)
        client = yield from ncplib.connect(
            "127.0.0.1", port,
            loop=self.loop,
            auto_link=client_auto_link,
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
        client = yield from self.createClient()
        self.assertIsInstance(client.transport, asyncio.WriteTransport)

    @asyncio.coroutine
    def testSend(self):
        client = yield from self.createClient()
        response = client.send("LINK", "ECHO", FOO="BAR")
        yield from self.assertMessages(response, "LINK", {"ECHO": {"FOO": "BAR"}})

    @asyncio.coroutine
    def testSendFiltersMessages(self):
        client = yield from self.createClient()
        client.send("JUNK", "JUNK", JUNK="JUNK")
        client.send("LINK", "ECHO", BAZ="QUX")
        response = client.send("LINK", "ECHO", FOO="BAR")
        yield from self.assertMessages(response, "LINK", {"ECHO": {"FOO": "BAR"}})

    @asyncio.coroutine
    def testSendPacket(self):
        client = yield from self.createClient()
        response = client.send_packet("LINK", ECHO={"FOO": "BAR"})
        yield from self.assertMessages(response, "LINK", {"ECHO": {"FOO": "BAR"}})

    @asyncio.coroutine
    def testRecvFieldConnectionFiltersMessages(self):
        client = yield from self.createClient()
        client.send("JUNK", "JUNK", JUNK="JUNK")
        client.send("LINK", "ECHO", FOO="BAR")
        field = yield from client.recv_field("LINK", "ECHO")
        self.assertEqual(field, {"FOO": "BAR"})

    @asyncio.coroutine
    def testRecvFieldResponseFiltersMessages(self):
        client = yield from self.createClient()
        client.send("LINK", "ECHO", BAZ="QUX")
        response = client.send("LINK", "ECHO", FOO="BAR")
        field = yield from response.recv_field("ECHO")
        self.assertEqual(field, {"FOO": "BAR"})

    @asyncio.coroutine
    def testBadRequest(self):
        client = yield from self.createClient()
        response = client.send("LINK", "BAD")
        with self.assertLogs("ncplib.server", "WARN"):
            with self.assertRaises(ncplib.CommandError) as cx:
                yield from response.recv()
        self.assertEqual(cx.exception.field.packet_type, "LINK")
        self.assertEqual(cx.exception.field.name, "BAD")
        self.assertEqual(cx.exception.detail, "Boom!")
        self.assertEqual(cx.exception.code, 400)

    @asyncio.coroutine
    def testServerError(self):
        client = yield from self.createClient()
        response = client.send("LINK", "BOOM")
        with self.assertLogs("ncplib.server", "WARN"):
            with self.assertRaises(ncplib.CommandError) as cx:
                yield from response.recv()
        self.assertEqual(cx.exception.field.packet_type, "LINK")
        self.assertEqual(cx.exception.field.name, "BOOM")
        self.assertEqual(cx.exception.detail, "Server error")
        self.assertEqual(cx.exception.code, 500)

    @asyncio.coroutine
    def testWarning(self):
        client = yield from self.createClient()
        response = client.send("LINK", "ECHO", WARN="Boom!", WARC=10)
        with self.assertWarns(ncplib.CommandWarning) as cx:
            yield from response.recv()
        self.assertEqual(cx.warning.field.packet_type, "LINK")
        self.assertEqual(cx.warning.field.name, "ECHO")
        self.assertEqual(cx.warning.detail, "Boom!")
        self.assertEqual(cx.warning.code, 10)

    @asyncio.coroutine
    def testAuthenticationError(self):
        client = yield from self.createClient(client_auto_auth=False)
        yield from client.recv_field("LINK", "HELO")
        client.send("LINK", "CCRE")
        with self.assertLogs("ncplib.server", "WARN"):
            with self.assertRaises(ncplib.CommandError) as cx:
                yield from client.recv()
        self.assertEqual(cx.exception.field.packet_type, "LINK")
        self.assertEqual(cx.exception.field.name, "CCRE")
        self.assertEqual(cx.exception.detail, "CIW - This field is required")
        self.assertEqual(cx.exception.code, 401)

    @asyncio.coroutine
    def testEncodeError(self):
        client = yield from self.createClient(client_auto_link=False)
        client._writer.write(b"Boom!" * 1024)
        client._writer.write_eof()
        with self.assertLogs("ncplib.server", "WARN"):
            with self.assertRaises(ncplib.CommandError) as cx:
                while True:
                    yield from client.recv()
        self.assertEqual(cx.exception.field.packet_type, "LINK")
        self.assertEqual(cx.exception.field.name, "ERRO")
        self.assertEqual(cx.exception.detail, "Bad request")
        self.assertEqual(cx.exception.code, 400)

    @asyncio.coroutine
    def testTopLevelServerError(self):
        with self.assertLogs("ncplib.server", "ERROR"):
            client = yield from self.createClient(error_server_handler)
            with self.assertRaises(ncplib.CommandError) as cx:
                yield from client.recv()
        self.assertEqual(cx.exception.field.packet_type, "LINK")
        self.assertEqual(cx.exception.field.name, "ERRO")
        self.assertEqual(cx.exception.detail, "Server error")
        self.assertEqual(cx.exception.code, 500)

    @asyncio.coroutine
    def testServerConnectionError(self):
        with self.assertLogs("ncplib.server", "ERROR"):
            with self.assertRaises(ncplib.CommandError) as cx:
                yield from self.createClient(error_server_handler, server_auto_auth=False)
        self.assertEqual(cx.exception.field.packet_type, "LINK")
        self.assertEqual(cx.exception.field.name, "ERRO")
        self.assertEqual(cx.exception.detail, "Server error")
        self.assertEqual(cx.exception.code, 500)

    @asyncio.coroutine
    def testConnectionWaitClosedDeprecated(self):
        client = yield from self.createClient()
        client.close()
        with self.assertWarns(DeprecationWarning):
            yield from client.wait_closed()

    @asyncio.coroutine
    def testClientGracefulDisconnect(self):
        client_disconnected_event = asyncio.Event(loop=self.loop)
        client = yield from self.createClient(partial(disconnect_server_handler, client_disconnected_event))
        # Ping a packet back and forth.
        response = client.send("LINK", "ECHO", FOO="bar")
        self.assertEqual((yield from response.recv())["FOO"], "bar")
        # Clost the client ahead of the server.
        yield from client.__aexit__(None, None, None)
        yield from client_disconnected_event.wait()

    @asyncio.coroutine
    def testClientApplication(self):
        port = yield from self.createServer()
        yield from ncplib.run_client(ClientApplication, "127.0.0.1", port, hostname="ncplib-test")

    @asyncio.coroutine
    def testClientApplicationTimeout(self):
        port = yield from self.createServer()
        with self.assertLogs("ncplib.client", "WARNING"):
            yield from ncplib.run_client(
                ClientApplication, "127.0.0.1", port,
                hostname="ncplib-test", connect_timeout=0,
            )

    @asyncio.coroutine
    def testClientApplicationDecodeError(self):
        port = yield from self.createServer(decode_error_server_handler)
        with self.assertLogs("ncplib.client", "WARNING"):
            yield from ncplib.run_client(ClientApplication, "127.0.0.1", port)

    @asyncio.coroutine
    def testClientApplicationCommandError(self):
        port = yield from self.createServer()
        with self.assertLogs("ncplib.client", "WARNING"):
            yield from ncplib.run_client(
                partial(ClientApplication, ERRC=401, ERRO="Boom!"), "127.0.0.1", port,
                hostname="ncplib-test",
            )
