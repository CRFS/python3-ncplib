import asyncio, os, warnings
from array import array
from unittest import TestCase, skipUnless

from ncplib.client import connect_sync
from ncplib.errors import PacketWarning


NCPLIB_TEST_CLIENT_HOST = os.environ.get("NCPLIB_TEST_CLIENT_HOST")
NCPLIB_TEST_CLIENT_PORT = os.environ.get("NCPLIB_TEST_CLIENT_PORT")


@skipUnless(NCPLIB_TEST_CLIENT_HOST, "NCPLIB_TEST_CLIENT_HOST not set in environ")
@skipUnless(NCPLIB_TEST_CLIENT_PORT, "NCPLIB_TEST_CLIENT_PORT not set in environ")
class ClientTest(TestCase):

    # Test lifecycle.

    def setUp(self):
        # Create a debug loop.
        warnings.simplefilter("default", ResourceWarning)
        warnings.simplefilter("ignore", PacketWarning)
        self.loop = asyncio.new_event_loop()
        self.loop.set_debug(True)
        asyncio.set_event_loop(None)
        # Connect the client.
        self.client = connect_sync(NCPLIB_TEST_CLIENT_HOST, NCPLIB_TEST_CLIENT_PORT, loop=self.loop, timeout=10)

    def tearDown(self):
        self.client.close()
        self.client.wait_closed()
        self.loop.close()

    # Test utils.

    def assertStatParams(self, params):
        self.assertIsInstance(params[b"OCON"], int)
        self.assertIsInstance(params[b"CADD"], str)
        self.assertIsInstance(params[b"CIDS"], str)
        self.assertIsInstance(params[b"RGPS"], str)
        self.assertIsInstance(params[b"ELOC"], int)

    def assertSwepParams(self, params):
        self.assertIsInstance(params[b"PDAT"], array)
        self.assertEqual(params[b"PDAT"].typecode, "B")

    def assertTimeParams(self, params):
        self.assertEqual(params[b"SAMP"], 4096)
        self.assertEqual(params[b"FCTR"], 1200)
        self.assertIsInstance(params[b"DIQT"], array)
        self.assertEqual(params[b"DIQT"].typecode, "h")
        self.assertEqual(len(params[b"DIQT"]), 8192)

    # Simple integration tests.

    def testStat(self):
        params = self.client.execute(b"NODE", b"STAT")
        self.assertStatParams(params)

    # Testing the read machinery.

    def testStatCommunicate(self):
        fields = self.client.communicate(b"NODE", {b"STAT": {}})
        self.assertStatParams(fields[b"STAT"])

    def testStatRecvAll(self):
        fields = self.client.send(b"NODE", {b"STAT": {}}).recv()
        self.assertStatParams(fields[b"STAT"])

    def testStatRecvAny(self):
        fields = self.client.send(b"NODE", {b"STAT": {}}).recv_any()
        self.assertStatParams(fields[b"STAT"])

    def testStatRecvField(self):
        params = self.client.send(b"NODE", {b"STAT": {}}).recv_field(b"STAT")
        self.assertStatParams(params)

    def testStatRecvFieldMissing(self):
        with self.assertRaises(ValueError):
            self.client.send(b"NODE", {b"STAT": {}}).recv_field(b"BOOM")

    # More complex commands with an ACK.

    def testDspcSwep(self):
        params = self.client.execute(b"DSPC", b"SWEP", timeout=30)
        self.assertSwepParams(params)

    def testDspcTime(self):
        params = self.client.execute(b"DSPC", b"TIME", {b"SAMP": 4096, b"FCTR": 1200}, timeout=30)
        self.assertTimeParams(params)

    # Loop tests.

    def testDsplSwep(self):
        streaming_response = self.client.send(b"DSPL", {b"SWEP": {}})
        params = streaming_response.recv_field(b"SWEP", timeout=30)
        self.assertSwepParams(params)
        params = streaming_response.recv_field(b"SWEP", timeout=30)
        self.assertSwepParams(params)

    def testDsplTime(self):
        streaming_response = self.client.send(b"DSPL", {b"TIME": {b"SAMP": 4096, b"FCTR": 1200}})
        params = streaming_response.recv_field(b"TIME", timeout=30)
        self.assertTimeParams(params)
        params = streaming_response.recv_field(b"TIME", timeout=30)
        self.assertTimeParams(params)
