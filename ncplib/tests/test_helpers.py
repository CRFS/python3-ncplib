import unittest
from hypothesis import given, strategies as st
from ncplib.tests.strategies import timestamps, uints
from ncplib.helpers import datetime_to_unix_nano, datetime_to_unix, unix_to_datetime, dbm_to_rssi, rssi_to_dbm


class HelpersTestCase(unittest.TestCase):

    # Datetimes.

    @given(timestamps())
    def testDatetimeToUnixNanoInvertsUnixToDatetime(self, value):
        time, nanotime = datetime_to_unix_nano(value)
        self.assertEqual(unix_to_datetime(time, nanotime, value.tzinfo), value)

    @given(uints())
    def testUnixToDatetimeInvertsDatetimeToUnix(self, value):
        self.assertEqual(datetime_to_unix(unix_to_datetime(value)), value)

    # Power levels.

    @given(uints(8), st.floats(min_value=-20, max_value=20.0))
    def testRssiToDbmInverts_DbmToRssi(self, value, ref_level):
        self.assertEqual(dbm_to_rssi(rssi_to_dbm(value, ref_level), ref_level), value)
