import os
from unittest import TestCase, skipUnless, SkipTest

from ncplib.client import connect_sync
from ncplib.errors import CommandError


NCPLIB_TEST_CLIENT_HOST = os.environ.get("NCPLIB_TEST_CLIENT_HOST")
NCPLIB_TEST_CLIENT_PORT = os.environ.get("NCPLIB_TEST_CLIENT_PORT")


@skipUnless(NCPLIB_TEST_CLIENT_HOST, "NCPLIB_TEST_CLIENT_HOST not set in environ")
@skipUnless(NCPLIB_TEST_CLIENT_PORT, "NCPLIB_TEST_CLIENT_PORT not set in environ")
class ClientTest(TestCase):

    def setUp(self):
        self.client = connect_sync(NCPLIB_TEST_CLIENT_HOST, NCPLIB_TEST_CLIENT_PORT, timeout=5)

    def testRunStat(self):
        response = self.client.run_node(b"STAT", timeout=5)
        self.assertIsInstance(response[b"OCON"], int)
        self.assertIsInstance(response[b"CADD"], str)
        self.assertIsInstance(response[b"CIDS"], str)
        self.assertIsInstance(response[b"RGPS"], str)
        self.assertIsInstance(response[b"ELOC"], int)

    def testRunSurvey(self):
        try:
            response = self.client.run_dsp_control(b"SURV", timeout=90)
            self.assertIn(b"JSON", response)
        except CommandError as ex:
            if ex.code == -4079:
                raise SkipTest("Survey already running on node.")

    def testStreamTimeCapture(self):
        with self.client.stream_dsp_loop_multi({b"TIME": {b"FCTR": 900, b"SAMP": 1024}}, timeout=5) as frequency_stream:
            response = frequency_stream.read_all(timeout=120)

    def tearDown(self):
        self.client.close()
        self.client.wait_closed()