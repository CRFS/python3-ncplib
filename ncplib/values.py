import warnings
from array import array
from collections import namedtuple
from enum import Enum, unique
from functools import singledispatch

from ncplib.errors import DecodeWarning


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


EncodedValue = namedtuple("EncodedValue", ("value", "type_id",))


class uint(int):

    __slots__ = ()


# Encoders.

class ValueEncoder:

    def __init__(self):
        self.encode = singledispatch(self.encode)
        # Register default types.
        self.register(EncodedValue, self.encode_encoded)
        self.register(int, self.encode_int)
        self.register(uint, self.encode_uint)
        self.register(str, self.encode_str)
        self.register(bytes, self.encode_bytes)
        self.register(bytearray, self.encode_bytes)
        self.register(memoryview, self.encode_bytes)
        self.register(array, self.encode_array)

    # Encoder registration.

    def register(self, cls, func):
        self.encode.register(cls, func)

    # Encoder functions.

    def encode(self, value):
        raise TypeError("Unsupported type", type(value))

    def encode_encoded(self, value):
        return value

    def encode_int(self, value):
        return EncodedValue(
            value = value.to_bytes(length=4, byteorder="little", signed=True),
            type_id = ValueType.i32.value,
        )
    def encode_uint(self, value):
        return EncodedValue(
            value = value.to_bytes(length=4, byteorder="little", signed=True),
            type_id = ValueType.u32.value,
        )

    def encode_str(self, value):
        return EncodedValue(
            value = value.encode(encoding="latin1", errors="ignore") + b"\x00",
            type_id = ValueType.string.value,
        )

    def encode_bytes(self, value):
        return EncodedValue(
            value = value,
            type_id = ValueType.raw.value,
        )

    def encode_array(self, value):
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
        return EncodedValue(
            value = value.tobytes(),
            type_id = type_id,
        )

default_value_encoder = ValueEncoder()


# Decoders.

class ValueDecoder:

    def __init__(self):
        self._registry = {}
        # Register default types.
        self.register(ValueType.i32.value, self.decode_i32)
        self.register(ValueType.u32.value, self.decode_u32)
        self.register(ValueType.string.value, self.decode_string)
        self.register(ValueType.raw.value, self.decode_raw)
        self.register(ValueType.array_u8.value, self.decode_array_u8)
        self.register(ValueType.array_u16.value, self.decode_array_u16)
        self.register(ValueType.array_u32.value, self.decode_array_u32)
        self.register(ValueType.array_i8.value, self.decode_array_i8)
        self.register(ValueType.array_i16.value, self.decode_array_i16)
        self.register(ValueType.array_i32.value, self.decode_array_i32)

    def register(self, type_id, decoder):
        self._registry[type_id] = decoder

    def decode(self, type_id, encoded_value):
        try:
            decoder = self._registry[type_id]
        except KeyError:
            warnings.warn(DecodeWarning("Unsupported type ID", type_id))
            return EncodedValue(
                value = encoded_value,
                type_id = type_id,
            )
        else:
            return decoder(encoded_value)

    def decode_i32(self, encoded_value):
        return int.from_bytes(encoded_value, byteorder="little", signed=True)

    def decode_u32(self, encoded_value):
        return uint.from_bytes(encoded_value, byteorder="little", signed=False)

    def decode_string(self, encoded_value):
        return encoded_value.split(b"\x00", 1)[0].decode(encoding="latin1", errors="ignore")

    def decode_raw(self, encoded_value):
        return encoded_value

    def decode_array_u8(self, encoded_value):
        return array("B", encoded_value)

    def decode_array_u16(self, encoded_value):
        return array("H", encoded_value)

    def decode_array_u32(self, encoded_value):
        return array("I", encoded_value)

    def decode_array_i8(self, encoded_value):
        return array("b", encoded_value)

    def decode_array_i16(self, encoded_value):
        return array("h", encoded_value)

    def decode_array_i32(self, encoded_value):
        return array("i", encoded_value)

default_value_decoder = ValueDecoder()
