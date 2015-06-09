import struct


HEADER_STRUCT = struct.Struct("<4s4sIIIIII")

FIELD_STRUCT = struct.Struct("<4s3sBI")

PARAM_STRUCT = struct.Struct("<4s3sB")

FOOTER_STRUCT = struct.Struct("<I4s")
