from datetime import datetime
from collections.abc import Mapping


class Packet:

    __slots__ = ("type", "id", "format", "timestamp", "fields",)

    def __init__(self, type, id, format, timestamp, fields):
        assert isinstance(type, str) and len(type) == 4
        assert isinstance(id, int)
        assert isinstance(format, int) and format == 1
        assert isinstance(timestamp, datetime) and datetime.tzinfo is not None
        assert isinstance(fields, Mapping)
        # Store the data.
        self.type = type
        self.id = id
        self.format = format
        self.timestamp = timestamp
        self.fields = fields
