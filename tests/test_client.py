import asyncio, os, warnings
from unittest import TestCase, skipUnless, SkipTest

from ncplib.client import connect_sync
from ncplib.errors import CommandError


NCPLIB_TEST_CLIENT_HOST = os.environ.get("NCPLIB_TEST_CLIENT_HOST")
NCPLIB_TEST_CLIENT_PORT = os.environ.get("NCPLIB_TEST_CLIENT_PORT")


@skipUnless(NCPLIB_TEST_CLIENT_HOST, "NCPLIB_TEST_CLIENT_HOST not set in environ")
@skipUnless(NCPLIB_TEST_CLIENT_PORT, "NCPLIB_TEST_CLIENT_PORT not set in environ")
class ClientTest(TestCase):

    # Test lifecycle.

    def setUp(self):
        # Create a debug loop.
        warnings.simplefilter("error", ResourceWarning)
        self.loop = asyncio.new_event_loop()
        self.loop.set_debug(True)
        asyncio.set_event_loop(self.loop)
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

    def testDsplSwep(self):
        streaming_response = self.client.send(b"DSPL", {b"SWEP": {}})
        streaming_response.read_field(b"SWEP", timeout=15)

    def testDsplTime(self):
        streaming_response = self.client.send(b"DSPL", {b"TIME": {b"FCTR": 1200}})
        streaming_response.read_field(b"TIME", timeout=15)
