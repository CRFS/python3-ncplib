import warnings
from array import array
from functools import singledispatch

from ncplib.errors import DecodeWarning
from ncplib.functional import valuedispatch


__all__ = (
    "uint",
)


# Known type codes.

TYPE_I32 = 0x00

TYPE_U32 = 0x01

TYPE_STRING = 0x02

TYPE_RAW = 0x80

TYPE_ARRAY_U8 = 0x81

TYPE_ARRAY_U16 = 0x82

TYPE_ARRAY_U32 = 0x83

TYPE_ARRAY_I8 = 0x84

TYPE_ARRAY_I16 = 0x85

TYPE_ARRAY_I32 = 0x86


# Type converters.

class uint(int):

    __slots__ = ()


# Encoders.

@singledispatch
def encode_value(value):
    raise TypeError("Unsupported value type {}".format(type(value)))

@encode_value.register(int)
def encode_value_int(value):
    return TYPE_I32, value.to_bytes(length=4, byteorder="little", signed=True)

@encode_value.register(uint)
def encode_value_uint(value):
    return TYPE_U32, value.to_bytes(length=4, byteorder="little", signed=False)

@encode_value.register(str)
def encode_value_str(value):
    return TYPE_STRING, value.encode(encoding="utf-8", errors="ignore") + b"\x00"

@encode_value.register(bytes)
@encode_value.register(bytearray)
@encode_value.register(memoryview)
def encode_value_bytes(value):
    return TYPE_RAW, value

ARRAY_TYPE_CODES_TO_TYPE_ID = {
    "B": TYPE_ARRAY_U8,
    "H": TYPE_ARRAY_U16,
    "I": TYPE_ARRAY_U32,
    "b": TYPE_ARRAY_I8,
    "h": TYPE_ARRAY_I16,
    "i": TYPE_ARRAY_I32,
}

@encode_value.register(array)
def encode_value_array(value):
    try:
        type_id = ARRAY_TYPE_CODES_TO_TYPE_ID[value.typecode]
    except KeyError:
        raise TypeError("Unsupported array type {}".format(value.typecode))
    return type_id, value.tobytes()


# Decoders.

@valuedispatch
def decode_value(type_id, encoded_value):
    warnings.warn(DecodeWarning("Unsupported type ID", type_id))
    return None

@decode_value.register(TYPE_I32)
def decode_value_i32(type_id, encoded_value):
    return int.from_bytes(encoded_value, byteorder="little", signed=True)

@decode_value.register(TYPE_U32)
def decode_value_u32(type_id, encoded_value):
    return uint.from_bytes(encoded_value, byteorder="little", signed=False)

@decode_value.register(TYPE_STRING)
def ddecode_value_string(type_id, encoded_value):
    return encoded_value.split(b"\x00", 1)[0].decode(encoding="utf-8", errors="ignore")

@decode_value.register(TYPE_RAW)
def decode_value_raw(type_id, encoded_value):
    return encoded_value

TYPE_ID_TO_ARRAY_TYPE_CODES = dict(map(reversed, ARRAY_TYPE_CODES_TO_TYPE_ID.items()))

@decode_value.register(TYPE_ARRAY_U8)
@decode_value.register(TYPE_ARRAY_U16)
@decode_value.register(TYPE_ARRAY_U32)
@decode_value.register(TYPE_ARRAY_I8)
@decode_value.register(TYPE_ARRAY_I16)
@decode_value.register(TYPE_ARRAY_I32)
def decode_value_array_u8(type_id, encoded_value):
    return array(TYPE_ID_TO_ARRAY_TYPE_CODES[type_id], encoded_value)
