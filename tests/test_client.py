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
        response = self.client.run_command(b"NODE", b"STAT", timeout=5)
        self.assertIsInstance(response[b"OCON"], int)
        self.assertIsInstance(response[b"CADD"], str)
        self.assertIsInstance(response[b"CIDS"], str)
        self.assertIsInstance(response[b"RGPS"], str)
        self.assertIsInstance(response[b"ELOC"], int)

    def testRunSurvey(self):
        try:
            response = self.client.run_command(b"DSPC", b"SURV", timeout=90)
            self.assertIn(b"JSON", response)
        except CommandError as ex:
            if ex.code == -4079:
                raise SkipTest("Survey already running on node.")

    def tearDown(self):
        self.client.close()
