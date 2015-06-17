import warnings
from array import array
from enum import Enum, unique
from functools import singledispatch

from ncplib.errors import DecodeWarning
from ncplib.functional import valuedispatch


__all__ = (
    "uint",
)


@unique
class ValueType(Enum):

    i32 = 0x00

    u32 = 0x01

    string = 0x02

    raw = 0x80

    array_u8 = 0x81

    array_u16 = 0x82

    array_u32 = 0x83

    array_i8 = 0x84

    array_i16 = 0x85

    array_i32 = 0x86


class uint(int):

    __slots__ = ()


# Encoders.

@singledispatch
def encode_value(value):
    raise TypeError("Unsupported type", type(value))

@encode_value.register(int)
def encode_int(value):
    return ValueType.i32.value, value.to_bytes(length=4, byteorder="little", signed=True)

@encode_value.register(uint)
def encode_uint(value):
    return ValueType.u32.value, value.to_bytes(length=4, byteorder="little", signed=True)

@encode_value.register(str)
def encode_str(value):
    return ValueType.string.value, value.encode(encoding="latin1", errors="ignore") + b"\x00"

@encode_value.register(bytes)
@encode_value.register(bytearray)
@encode_value.register(memoryview)
def encode_bytes(value):
    return ValueType.raw.value, value

@encode_value.register(array)
def encode_array(value):
    try:
        type_id = {
            "B": ValueType.array_u8.value,
            "H": ValueType.array_u16.value,
            "I": ValueType.array_u32.value,
            "b": ValueType.array_i8.value,
            "h": ValueType.array_i16.value,
            "i": ValueType.array_i32.value,
        }[value.typecode]
    except KeyError:
        raise TypeError("Unsupported array type", value.typecode)
    return type_id, value.tobytes()


# Decoders.

@valuedispatch
def decode_value(type_id, encoded_value):
    warnings.warn(DecodeWarning("Unsupported type ID", type_id))
    return None

@decode_value.register(ValueType.i32.value)
def decode_i32(type_id, encoded_value):
    return int.from_bytes(encoded_value, byteorder="little", signed=True)

@decode_value.register(ValueType.u32.value)
def decode_u32(type_id, encoded_value):
    return uint.from_bytes(encoded_value, byteorder="little", signed=False)

@decode_value.register(ValueType.string.value)
def decode_string(type_id, encoded_value):
    return encoded_value.split(b"\x00", 1)[0].decode(encoding="latin1", errors="ignore")

@decode_value.register(ValueType.raw.value)
def decode_raw(type_id, encoded_value):
    return encoded_value

@decode_value.register(ValueType.array_u8.value)
def decode_array_u8(type_id, encoded_value):
    return array("B", encoded_value)

@decode_value.register(ValueType.array_u16.value)
def decode_array_u16(type_id, encoded_value):
    return array("H", encoded_value)

@decode_value.register(ValueType.array_u32.value)
def decode_array_u32(type_id, encoded_value):
    return array("I", encoded_value)

@decode_value.register(ValueType.array_i8.value)
def decode_array_i8(type_id, encoded_value):
    return array("b", encoded_value)

@decode_value.register(ValueType.array_i16.value)
def decode_array_i16(type_id, encoded_value):
    return array("h", encoded_value)

@decode_value.register(ValueType.array_i32.value)
def decode_array_i32(type_id, encoded_value):
    return array("i", encoded_value)
