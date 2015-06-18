import asyncio, os, warnings
from array import array
from unittest import TestCase, skipUnless

from ncplib.client import connect_sync
from ncplib.errors import CommandWarning


NCPLIB_TEST_CLIENT_HOST = os.environ.get("NCPLIB_TEST_CLIENT_HOST")
NCPLIB_TEST_CLIENT_PORT = os.environ.get("NCPLIB_TEST_CLIENT_PORT")


@skipUnless(NCPLIB_TEST_CLIENT_HOST, "NCPLIB_TEST_CLIENT_HOST not set in environ")
@skipUnless(NCPLIB_TEST_CLIENT_PORT, "NCPLIB_TEST_CLIENT_PORT not set in environ")
class ClientTest(TestCase):

    # Test lifecycle.

    def setUp(self):
        # Create a debug loop.
        warnings.simplefilter("default", ResourceWarning)
        warnings.simplefilter("ignore", CommandWarning)
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
        self.assertIsInstance(params["OCON"], int)
        self.assertIsInstance(params["CADD"], str)
        self.assertIsInstance(params["CIDS"], str)
        self.assertIsInstance(params["RGPS"], str)
        self.assertIsInstance(params["ELOC"], int)

    def assertSwepParams(self, params):
        self.assertIsInstance(params["PDAT"], array)
        self.assertEqual(params["PDAT"].typecode, "B")

    def assertTimeParams(self, params):
        self.assertEqual(params["SAMP"], 4096)
        self.assertEqual(params["FCTR"], 1200)
        self.assertIsInstance(params["DIQT"], array)
        self.assertEqual(params["DIQT"].typecode, "h")
        self.assertEqual(len(params["DIQT"]), 8192)

    # Simple integration tests.

    def testStat(self):
        params = self.client.execute("NODE", "STAT")
        self.assertStatParams(params)

    # Testing the read machinery.

    def testStatRecvField(self):
        params = self.client.send("NODE", {"STAT": {}}).recv_field("STAT")
        self.assertStatParams(params)

    # More complex commands with an ACK.

    def testDspcSwep(self):
        params = self.client.execute("DSPC", "SWEP", timeout=30)
        self.assertSwepParams(params)

    def testDspcTime(self):
        params = self.client.execute("DSPC", "TIME", {"SAMP": 4096, "FCTR": 1200}, timeout=30)
        self.assertTimeParams(params)

    # Loop tests.

    def testDsplSwep(self):
        streaming_response = self.client.send("DSPL", {"SWEP": {}})
        params = streaming_response.recv_field("SWEP", timeout=30)
        self.assertSwepParams(params)
        params = streaming_response.recv_field("SWEP", timeout=30)
        self.assertSwepParams(params)

    def testDsplTime(self):
        streaming_response = self.client.send("DSPL", {"TIME": {"SAMP": 4096, "FCTR": 1200}})
        params = streaming_response.recv_field("TIME", timeout=30)
        self.assertTimeParams(params)
        params = streaming_response.recv_field("TIME", timeout=30)
        self.assertTimeParams(params)
