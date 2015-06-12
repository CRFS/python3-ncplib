import os
from unittest import TestCase, skipUnless

from ncplib.client import connect_sync


NCPLIB_TEST_CLIENT_HOST = os.environ.get("NCPLIB_TEST_CLIENT_HOST")
NCPLIB_TEST_CLIENT_PORT = os.environ.get("NCPLIB_TEST_CLIENT_PORT")


@skipUnless(NCPLIB_TEST_CLIENT_HOST, "NCPLIB_TEST_CLIENT_HOST not set in environ")
@skipUnless(NCPLIB_TEST_CLIENT_PORT, "NCPLIB_TEST_CLIENT_PORT not set in environ")
class ClientTest(TestCase):

    def setUp(self):
        self.client = connect_sync(NCPLIB_TEST_CLIENT_HOST, NCPLIB_TEST_CLIENT_PORT, timeout=10)

    def testExecuteStat(self):
        status_info = self.client.communicate(b"NODE", {b"STAT": {}})
        self.assertEqual(status_info.type, b"NODE")
        self.assertIn(b"STAT", status_info.fields)
        self.assertIn(b"OCON", status_info.fields[b"STAT"])
        self.assertIsInstance(status_info.fields[b"STAT"][b"OCON"], int)
        self.assertIn(b"CADD", status_info.fields[b"STAT"])
        self.assertIsInstance(status_info.fields[b"STAT"][b"CADD"], str)
        self.assertIn(b"CIDS", status_info.fields[b"STAT"])
        self.assertIsInstance(status_info.fields[b"STAT"][b"CIDS"], str)
        self.assertIn(b"RGPS", status_info.fields[b"STAT"])
        self.assertIsInstance(status_info.fields[b"STAT"][b"RGPS"], str)
        self.assertIn(b"ELOC", status_info.fields[b"STAT"])
        self.assertIsInstance(status_info.fields[b"STAT"][b"ELOC"], int)

    def tearDown(self):
        self.client.close()
