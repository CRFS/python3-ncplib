import unittest
from datetime import datetime, timedelta, timezone
from itertools import product
from ncplib.helpers import datetime_to_unix_nano, datetime_to_unix, unix_to_datetime, dbm_to_rssi, rssi_to_dbm


TIMESTAMP_VALUES = [
    datetime(1970, 1, 1, 0, 0, tzinfo=timezone.utc),
    datetime.now(tz=timezone.utc),
    datetime(2100, 12, 31, 23, 59, 59, tzinfo=timezone.utc),
]


class DatetimeTestCase(unittest.TestCase):

    def testDatetimeToUnixNano(self):
        for timestamp in TIMESTAMP_VALUES:
            with self.subTest(timestamp=timestamp):
                time, nanotime = datetime_to_unix_nano(timestamp)
                self.assertEqual(unix_to_datetime(time, nanotime, timestamp.tzinfo), timestamp)

    def testDatetimeToUnix(self):
        for timestamp in TIMESTAMP_VALUES:
            timestamp = timestamp - timedelta(microseconds=timestamp.microsecond)  # Round to nearest second.
            with self.subTest(timestamp=timestamp):
                time = datetime_to_unix(timestamp)
                self.assertEqual(unix_to_datetime(time, tz=timestamp.tzinfo), timestamp)


RSSI_VALUES = [0, 10, 2 ** 8 - 1]

REF_LEVEL_VALUES = [-20, 0, 10, 20]


class PowerLevelTestCase(unittest.TestCase):

    def testRssiToDbm(self):
        for rssi, ref_level in product(RSSI_VALUES, REF_LEVEL_VALUES):
            for ref_level in REF_LEVEL_VALUES:
                with self.subTest(rssi=rssi, ref_level=ref_level):
                    self.assertEqual(dbm_to_rssi(rssi_to_dbm(rssi, ref_level), ref_level), rssi)
