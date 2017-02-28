from datetime import datetime, timezone


__all__ = (
    "datetime_to_unix",
    "unix_to_datetime",
)


# Datetimes.

def datetime_to_unix(value_datetime):
    value_datetime = value_datetime.astimezone(timezone.utc)
    return int(value_datetime.timestamp()), value_datetime.microsecond * 1000


def unix_to_datetime(value_unix, value_nano):
    return datetime.fromtimestamp(value_unix, tz=timezone.utc).replace(microsecond=value_nano // 1000)
