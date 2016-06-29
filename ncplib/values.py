"""
Value types
===========

.. currentmodule:: ncplib

Overview
--------

NCP data types are mapped onto python types as follows:

=========== ================================================
NCP type    Python type
=========== ================================================
int32       :class:`int`
uint32      :class:`ncplib.uint`
string      :class:`str`
raw         :class:`bytes`
data int8   :class:`array.array(typecode="b") <array.array>`
data int16  :class:`array.array(typecode="h") <array.array>`
data int32  :class:`array.array(typecode="i") <array.array>`
data uint8  :class:`array.array(typecode="B") <array.array>`
data uint16 :class:`array.array(typecode="H") <array.array>`
data uint32 :class:`array.array(typecode="I") <array.array>`
=========== ================================================


API reference
-------------

.. autoclass:: uint
    :members:
"""


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

    """
    An unsigned integer value.

    Python does not distinguish between signed and unsigned integers, but :term:`NCP` encodes them differently.
    Additionally, the binary encoding restricts the ranges of signed and unsigned integers:

    -   ``-2 ** 31 <= int32 <= 2 ** 31 - 1``
    -   ``0 <= uint32 <= 2 ** 32 - 1``

    To distinguish between ``int32`` and ``uint32`` in :term:`NCP parameter` values, wrap any :class:`int` values to be
    encoded as ``uint32`` in :class:`uint`.
    """

    __slots__ = ()

    def __new__(cls, value):
        if not 0 <= value <= 4294967295:
            raise ValueError("Out of range for unsigned 32 bit integer: {!r}".format(value))
        return super().__new__(cls, value)


# Encoders.

@singledispatch
def encode_value(value):  # pragma: no cover
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
        return ARRAY_TYPE_CODES_TO_TYPE_ID[value.typecode], value.tobytes()
    except KeyError:  # pragma: no cover
        raise TypeError("Unsupported array type {}".format(value.typecode))


# Decoders.

@valuedispatch
def decode_value(type_id, encoded_value):  # pragma: no cover
    warnings.warn(DecodeWarning("Unsupported type ID", type_id))
    return encoded_value


@decode_value.register(TYPE_I32)
def decode_value_i32(type_id, encoded_value):
    return int.from_bytes(encoded_value, byteorder="little", signed=True)


@decode_value.register(TYPE_U32)
def decode_value_u32(type_id, encoded_value):
    return uint.from_bytes(encoded_value, byteorder="little", signed=False)


@decode_value.register(TYPE_STRING)
def decode_value_string(type_id, encoded_value):
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
