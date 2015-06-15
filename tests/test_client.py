import os
from unittest import TestCase, skipUnless

from ncplib.client import connect_sync


NCPLIB_TEST_CLIENT_HOST = os.environ.get("NCPLIB_TEST_CLIENT_HOST")
NCPLIB_TEST_CLIENT_PORT = os.environ.get("NCPLIB_TEST_CLIENT_PORT")


@skipUnless(NCPLIB_TEST_CLIENT_HOST, "NCPLIB_TEST_CLIENT_HOST not set in environ")
@skipUnless(NCPLIB_TEST_CLIENT_PORT, "NCPLIB_TEST_CLIENT_PORT not set in environ")
class ClientTest(TestCase):

    def setUp(self):
        self.client = connect_sync(NCPLIB_TEST_CLIENT_HOST, NCPLIB_TEST_CLIENT_PORT, timeout=5)

    def testExecuteStat(self):
        response = self.client.run_command(b"NODE", b"STAT")
        self.assertIn(b"OCON", response[b"STAT"])
        self.assertIsInstance(response[b"STAT"][b"OCON"], int)
        self.assertIn(b"CADD", response[b"STAT"])
        self.assertIsInstance(response[b"STAT"][b"CADD"], str)
        self.assertIn(b"CIDS", response[b"STAT"])
        self.assertIsInstance(response[b"STAT"][b"CIDS"], str)
        self.assertIn(b"RGPS", response[b"STAT"])
        self.assertIsInstance(response[b"STAT"][b"RGPS"], str)
        self.assertIn(b"ELOC", response[b"STAT"])
        self.assertIsInstance(response[b"STAT"][b"ELOC"], int)

    def tearDown(self):
        self.client.close()
