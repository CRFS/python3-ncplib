import unittest
from datetime import datetime, timedelta, timezone
from ncplib.helpers import datetime_to_unix, unix_to_datetime


TIMESTAMP_VALUES = [
    datetime(1970, 1, 1, 0, 0, tzinfo=timezone.utc),
    datetime.now(tz=timezone.utc),
    datetime(2100, 12, 31, 23, 59, 59, tzinfo=timezone.utc),
]


class DatetimeTestCase(unittest.TestCase):

    def testDatetimeToUnixNano(self):
        for timestamp in TIMESTAMP_VALUES:
            with self.subTest(timestamp=timestamp):
                time, nanotime = datetime_to_unix(timestamp)
                self.assertEqual(unix_to_datetime(time, nanotime), timestamp)

    def testDatetimeToUnix(self):
        for timestamp in TIMESTAMP_VALUES:
            timestamp = timestamp - timedelta(microseconds=timestamp.microsecond)  # Round to nearest second.
            with self.subTest(timestamp=timestamp):
                time, nanotime = datetime_to_unix(timestamp)
                self.assertEqual(unix_to_datetime(time, nanotime), timestamp)
