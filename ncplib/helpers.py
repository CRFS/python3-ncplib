from datetime import datetime, timedelta, timezone
from math import floor


__all__ = (
    "datetime_to_unix_nano",
    "datetime_to_unix",
    "unix_to_datetime",
    "dbm_to_rssi",
    "rssi_to_dbm",
)


# Datetimes.

def datetime_to_unix_nano(value_datetime):
    value_datetime = value_datetime.astimezone(timezone.utc)
    return int(floor(value_datetime.timestamp())), int(value_datetime.microsecond * 1000),


def datetime_to_unix(value_datetime):
    return datetime_to_unix_nano(value_datetime)[0]


def unix_to_datetime(value_unix, value_nano=0, tz=timezone.utc):
    return datetime.fromtimestamp(value_unix, tz=tz) + timedelta(microseconds=value_nano // 1000)


# Power levels.

def dbm_to_rssi(value_dbm, ref_level=0.0):
    return int(round((value_dbm - float(ref_level) + 127.5) * 2.0))


def rssi_to_dbm(value_rssi, ref_level=0.0):
    return (float(value_rssi) / 2.0) - 127.5 + float(ref_level)
