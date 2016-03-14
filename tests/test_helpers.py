from hypothesis import given
from hypothesis.strategies import floats
from .conftest import timestamps, uints

from ncplib.helpers import datetime_to_unix_nano, datetime_to_unix, unix_to_datetime, dbm_to_rssi, rssi_to_dbm


# Datetimes.

@given(timestamps())
def test_datetime_to_unix_nano_inverts_unix_to_datetime(value):
    time, nanotime = datetime_to_unix_nano(value)
    assert unix_to_datetime(time, nanotime, value.tzinfo) == value


@given(uints())
def test_unix_to_datetime_inverts_datetime_to_unix(value):
    assert datetime_to_unix(unix_to_datetime(value)) == value


# Power levels.

@given(uints(8), floats(min_value=-20, max_value=20.0))
def test_rssi_to_dbm_inverts_dbm_to_rssi(value, ref_level):
    assert dbm_to_rssi(rssi_to_dbm(value, ref_level), ref_level) == value
