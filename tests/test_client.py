import asyncio, os, warnings
from array import array
from functools import wraps
from unittest import TestCase, skipUnless

from ncplib.client import connect
from ncplib.errors import CommandWarning


NCPLIB_TEST_CLIENT_HOST = os.environ.get("NCPLIB_TEST_CLIENT_HOST")
NCPLIB_TEST_CLIENT_PORT = os.environ.get("NCPLIB_TEST_CLIENT_PORT")


def require_loop(func):
    @wraps(func)
    def do_require_loop(self):
        # Set up debug warnings.
        with warnings.catch_warnings():
            warnings.simplefilter("default", ResourceWarning)
            warnings.simplefilter("ignore", CommandWarning)
            # Remove the global event loop, as proof that the library doesn't require it.
            # No way to do this nicely and restore it after the test, but this shouldn't
            # matter for the purposes of testing.
            asyncio.set_event_loop(None)
            # Set up a debug loop.
            loop = asyncio.new_event_loop()
            try:
                loop.set_debug(True)
                loop.run_until_complete(asyncio.wait_for(func(self, loop), loop=loop, timeout=30))
            finally:
                loop.close()
    return do_require_loop


def require_client(func):
    @wraps(func)
    @asyncio.coroutine
    def do_require_client(self, loop):
        # Connect the client.
        client = yield from connect(NCPLIB_TEST_CLIENT_HOST, NCPLIB_TEST_CLIENT_PORT, loop=loop)
        try:
            yield from func(self, loop, client)
        finally:
            client.close()
            yield from client.wait_closed()
    return do_require_client


@skipUnless(NCPLIB_TEST_CLIENT_HOST, "NCPLIB_TEST_CLIENT_HOST not set in environ")
@skipUnless(NCPLIB_TEST_CLIENT_PORT, "NCPLIB_TEST_CLIENT_PORT not set in environ")
class ClientTest(TestCase):

    # Test utils.

    def assertStatParams(self, params):
        self.assertIsInstance(params["OCON"], int)
        self.assertIsInstance(params["CADD"], str)
        self.assertIsInstance(params["CIDS"], str)
        self.assertIsInstance(params["RGPS"], str)
        self.assertIsInstance(params["ELOC"], int)

    def assertSwepParams(self, params):
        self.assertIsInstance(params["PDAT"], array)
        self.assertEqual(params["PDAT"].typecode, "B")

    def assertTimeParams(self, params):
        self.assertEqual(params["SAMP"], 1024)
        self.assertEqual(params["FCTR"], 1200)
        self.assertIsInstance(params["DIQT"], array)
        self.assertEqual(params["DIQT"].typecode, "h")
        self.assertEqual(len(params["DIQT"]), 2048)

    # Simple integration tests.

    @require_loop
    @require_client
    @asyncio.coroutine
    def testStat(self, loop, client):
        params = yield from client.execute("NODE", "STAT")
        self.assertStatParams(params)

    # Testing the read machinery.

    @require_loop
    @require_client
    @asyncio.coroutine
    def testStatRecvField(self, loop, client):
        params = yield from client.send("NODE", {"STAT": {}}).recv_field("STAT")
        self.assertStatParams(params)

    # More complex commands with an ACK.

    @require_loop
    @require_client
    @asyncio.coroutine
    def testDspcSwep(self, loop, client):
        params = yield from client.execute("DSPC", "SWEP")
        self.assertSwepParams(params)

    @require_loop
    @require_client
    @asyncio.coroutine
    def testDspcTime(self, loop, client):
        params = yield from client.execute("DSPC", "TIME", {"SAMP": 1024, "FCTR": 1200})
        self.assertTimeParams(params)

    # Combination commands.

    @require_loop
    @require_client
    @asyncio.coroutine
    def testMultiCommands(self, loop, client):
        response = client.send("DSPC", {"SWEP": {}, "TIME": {"SAMP": 1024, "FCTR": 1200}})
        swep_params, time_params = yield from asyncio.gather(response.recv_field("SWEP"), response.recv_field("TIME"), loop=loop)
        self.assertSwepParams(swep_params)
        self.assertTimeParams(time_params)

    # Loop tests.

    @require_loop
    @require_client
    @asyncio.coroutine
    def testDsplSwep(self, loop, client):
        response = client.send("DSPL", {"SWEP": {}})
        params = yield from response.recv_field("SWEP")
        self.assertSwepParams(params)
        params = yield from response.recv_field("SWEP")
        self.assertSwepParams(params)

    @require_loop
    @require_client
    @asyncio.coroutine
    def testDsplTime(self, loop, client):
        response = client.send("DSPL", {"TIME": {"SAMP": 1024, "FCTR": 1200}})
        params = yield from response.recv_field("TIME")
        self.assertTimeParams(params)
        params = yield from response.recv_field("TIME")
        self.assertTimeParams(params)
