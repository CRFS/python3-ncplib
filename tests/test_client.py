import asyncio, os, warnings
from array import array
from unittest import TestCase, skipUnless, SkipTest

from ncplib.client import connect_sync
from ncplib.errors import CommandError, CommandWarning


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
        self.client = connect_sync(NCPLIB_TEST_CLIENT_HOST, NCPLIB_TEST_CLIENT_PORT, loop=self.loop, timeout=5)

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

    def testStatCommunicate(self):
        fields = self.client.communicate(b"NODE", {b"STAT": {}})
        self.assertStatParams(fields[b"STAT"])

    # Testing the read machinery.

    def testStatReadAll(self):
        fields = self.client.send(b"NODE", {b"STAT": {}}).read_all()
        self.assertStatParams(fields[b"STAT"])

    def testStatReadAny(self):
        fields = self.client.send(b"NODE", {b"STAT": {}}).read_any()
        self.assertStatParams(fields[b"STAT"])

    def testStatReadField(self):
        params = self.client.send(b"NODE", {b"STAT": {}}).read_field(b"STAT")
        self.assertStatParams(params)

    def testStatReadFieldMissing(self):
        with self.assertRaises(ValueError):
            self.client.send(b"NODE", {b"STAT": {}}).read_field(b"BOOM")

    # More complex commands with an ACK and non-overlapping runtimes.

    def testDspcSurv(self):
        response = self.client.send(b"DSPC", {b"SURV": {}})
        response_2 = self.client.send(b"DSPC", {b"SURV": {}})
        # The second survey should have errored.
        with self.assertRaises(CommandError) as cm:
            response_2.read_field(b"SURV")
        self.assertEqual(cm.exception.code, -4079)
        # The first survey will probably succeed.
        try:
            params = response.read_field(b"SURV", timeout=90)
            self.assertIn(b"JSON", params)
        except CommandError as ex:
            # If the first survey errored, then someone else is also testing, so let's stop here.
            if ex.code == -4079:
                raise SkipTest("Survey already running on node.")

    def testDspcSwep(self):
        params = self.client.communicate(b"DSPC", {b"SWEP": {}}, timeout=15)[b"SWEP"]
        self.assertSwepParams(params)

    def testDspcTime(self):
        params = self.client.communicate(b"DSPC", {b"TIME": {b"SAMP": 4096, b"FCTR": 1200}}, timeout=15)[b"TIME"]
        self.assertTimeParams(params)

    # Loop tests.

    def testDsplSwep(self):
        streaming_response = self.client.send(b"DSPL", {b"SWEP": {}})
        params = streaming_response.read_field(b"SWEP", timeout=15)
        self.assertSwepParams(params)
        params = streaming_response.read_field(b"SWEP", timeout=15)
        self.assertSwepParams(params)

    def testDsplTime(self):
        streaming_response = self.client.send(b"DSPL", {b"TIME": {b"SAMP": 4096, b"FCTR": 1200}})
        params = streaming_response.read_field(b"TIME", timeout=15)
        self.assertTimeParams(params)
        params = streaming_response.read_field(b"TIME", timeout=15)
        self.assertTimeParams(params)
