from collections import namedtuple


Packet = namedtuple("Packet", ("type", "id", "timestamp", "info", "fields"))


RawParamValue = namedtuple("ParamValue", ("value", "type_id"))
