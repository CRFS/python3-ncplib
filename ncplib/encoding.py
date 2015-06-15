from array import array
from collections import namedtuple, OrderedDict
from datetime import datetime, timedelta, timezone
from enum import Enum
from functools import partial
from operator import methodcaller
from struct import Struct

from ncplib.errors import DecodeError


# Packet structs.

PACKET_HEADER_STRUCT = Struct("<4s4sIIIII4s")

FIELD_HEADER_STRUCT = Struct("<4s3sBI")

PARAM_HEADER_STRUCT = Struct("<4s3sB")

PACKET_FOOTER_STRUCT = Struct("<I4s")


# Packet constants.

PACKET_HEADER = b"\xdd\xcc\xbb\xaa"

PACKET_FOOTER = b"\xaa\xbb\xcc\xdd"


# Value encoders.

encode_i32 = partial(methodcaller("to_bytes"), length=4, byteorder="little", signed=True)

encode_u32 = partial(methodcaller("to_bytes"), length=4, byteorder="little", signed=False)

def encode_string(value):
    return value.encode(encoding="latin1", errors="ignore") + b"\x00"

encode_raw = bytes

encode_array_any = methodcaller("tobytes")


# Value decoders.

decode_i32 = partial(int.from_bytes, byteorder="little", signed=True)

decode_u32 = partial(int.from_bytes, byteorder="little", signed=False)

decode_string = partial(str, encoding="latin1", errors="ignore")

decode_raw = bytes

decode_array_u8 = partial(array, "B")

decode_array_u16 = partial(array, "H")

decode_array_u32 = partial(array, "I")

decode_array_i8 = partial(array, "b")

decode_array_i16 = partial(array, "h")

decode_array_i32 = partial(array, "i")


# Value types.

class Type(Enum):

    i32 = (0x00, encode_i32, decode_i32)

    u32 = (0x01, encode_u32, decode_u32)

    string = (0x02, encode_string, decode_string)

    raw = (0x80, encode_raw, decode_raw)

    array_u8 = (0x81, encode_array_any, decode_array_u8)

    array_u16 = (0x82, encode_array_any, decode_array_u16)

    array_u32 = (0x83, encode_array_any, decode_array_u32)

    array_i8 = (0x84, encode_array_any, decode_array_i8)

    array_i16 = (0x85, encode_array_any, decode_array_i16)

    array_i32 = (0x86, encode_array_any, decode_array_i32)

    def __init__(self, type_id, encode, decode):
        self.type_id = type_id
        self.encode = encode
        self.decode = decode


# Type detection.

ARRAY_TYPE_TO_TYPE = {
    "B": Type.array_u8,
    "H": Type.array_u16,
    "I": Type.array_u32,
    "b": Type.array_i8,
    "h": Type.array_i16,
    "i": Type.array_i32,
}

def get_array_type(value):
    try:
        return ARRAY_TYPE_TO_TYPE[value.typecode]
    except KeyError:
        raise TypeError("Unsupported array type", value.typecode)

def get_static_type(type, value):
    return type

PYTHON_TYPE_TO_TYPE_GETTER = {
    int: partial(get_static_type, Type.i32),
    str: partial(get_static_type, Type.string),
    bytes: partial(get_static_type, Type.raw),
    bytearray: partial(get_static_type, Type.raw),
    memoryview: partial(get_static_type, Type.raw),
    array: get_array_type,
}

def get_type_getter(value):
    try:
        return PYTHON_TYPE_TO_TYPE_GETTER[type(value)]
    except KeyError:
        raise TypeError("Unsupported type", type(value))

def get_type(value):
    return get_type_getter(value)(value)


# Value encoding.

EncodedValue = namedtuple("EncodedValue", ("value", "type_id",))

def encode_value(value):
    if isinstance(value, EncodedValue):
        return value
    value_type = get_type(value)
    value_encoded = value_type.encode(value)
    return EncodedValue(
        value = value_encoded,
        type_id = value_type.type_id,
    )


# Value decoding.

TYPE_ID_TO_TYPE = {
    member.type_id: member
    for member
    in Type
}

def get_type_decoder(type_id):
    try:
        return TYPE_ID_TO_TYPE[type_id].decode
    except KeyError:
        return partial(EncodedValue, type_id=type_id)

def decode_value(type_id, value):
    return get_type_decoder(type_id)(value)


# u24 size encoding.

def encode_u24_size(value):
    return (value // 4).to_bytes(length=4, byteorder="little", signed=False)


# u24 size decoding.

def decode_u24_size(value):
    return int.from_bytes(value, byteorder="little", signed=False) * 4


# Param encoding.

def encode_params(params):
    buf = bytearray()
    for name, value in params.items():
        encoded_value = encode_value(value)
        size = PARAM_HEADER_STRUCT.size + len(encoded_value.value)
        padding_size = size % 4
        buf.extend(PARAM_HEADER_STRUCT.pack(
            name,
            encode_u24_size(size + padding_size),
            encoded_value.type_id,
        ))
        buf.extend(encoded_value.value)
        buf.extend(b"\x00" * padding_size)
    return buf


# Param decoding.

def decode_params(buf, offset, limit):
    while offset < limit:
        name, u24_size, type_id = PARAM_HEADER_STRUCT.unpack_from(buf, offset)
        size = decode_u24_size(u24_size)
        value_encoded = bytes(buf[offset+PARAM_HEADER_STRUCT.size:offset+size]).split(b"\x00", 1)[0]
        value = decode_value(type_id, value_encoded)
        yield name, value
        offset += size
    if offset > limit:
        raise DecodeError("Parameter overflow by {} bytes".format(offset - limit))


# Field encoding.

Field = namedtuple("Field", ("name", "id", "params",))


def encode_fields(fields):
    buf = bytearray()
    for field in fields:
        encoded_params = encode_params(field.params)
        buf.extend(FIELD_HEADER_STRUCT.pack(
            field.name,
            encode_u24_size(FIELD_HEADER_STRUCT.size + len(encoded_params)),
            0,  # Field type ID is ignored.
            field.id,
        ))
        buf.extend(encoded_params)
    return buf


# Field decoding.

def decode_fields(buf, offset, limit):
    while offset < limit:
        name, u24_size, type_id, field_id = FIELD_HEADER_STRUCT.unpack_from(buf, offset)
        size = decode_u24_size(u24_size)
        params = OrderedDict(decode_params(buf, offset+FIELD_HEADER_STRUCT.size, offset+size))
        yield Field(
            name = name,
            id = field_id,
            params = params,
        )
        offset += size
    if offset > limit:
        raise DecodeError("Field overflow by {} bytes".format(offset - limit))


# Packet formats.

PACKET_FORMAT_ID = 1


# Packet encoding.

def encode_packet(packet_type, packet_id, timestamp, info, fields):
    encoded_fields = encode_fields(fields)
    # Encode the header.
    buf = bytearray()
    timestamp = timestamp.astimezone(timezone.utc)
    buf.extend(PACKET_HEADER_STRUCT.pack(
        PACKET_HEADER,
        packet_type,
        (PACKET_HEADER_STRUCT.size + len(encoded_fields) + PACKET_FOOTER_STRUCT.size) // 4,
        packet_id,
        PACKET_FORMAT_ID,
        int(timestamp.timestamp()),
        int(timestamp.microsecond * 1000),
        info,
    ))
    # Write the packet fields.
    buf.extend(encoded_fields)
    # Encode the packet footer.
    buf.extend(PACKET_FOOTER_STRUCT.pack(
        0,  # No checksum.
        PACKET_FOOTER,
    ))
    # All done!
    return buf


# Packet decoding.

Packet = namedtuple("Packet", ("type", "id", "timestamp", "info", "fields",))

def decode_packet_cps(header_buf):
    (
        header,
        packet_type,
        size_words,
        packet_id,
        format_id,
        time,
        nanotime,
        info,
    ) = PACKET_HEADER_STRUCT.unpack(header_buf)
    size = size_words * 4
    assert header == PACKET_HEADER
    timestamp = datetime.fromtimestamp(time, tz=timezone.utc) + timedelta(microseconds=nanotime // 1000)
    # Check the packet format.
    assert format_id == PACKET_FORMAT_ID
    # Decode the rest of the body data.
    size_remaining = size - PACKET_HEADER_STRUCT.size
    def decode_packet_body(body_buf):
        fields = list(decode_fields(body_buf, 0, size_remaining - PACKET_FOOTER_STRUCT.size))
        (
            checksum,
            footer,
        ) = PACKET_FOOTER_STRUCT.unpack_from(body_buf, size_remaining - PACKET_FOOTER_STRUCT.size)
        assert footer == PACKET_FOOTER
        # All done!
        return Packet(
            type = packet_type,
            id = packet_id,
            timestamp = timestamp,
            info = info,
            fields = fields,
        )
    # Return the number of bytes to read, and the function to finish decoding.
    return size_remaining, decode_packet_body


def decode_packet(buf):
    body_size, decode_packet_body = decode_packet_cps(buf[:PACKET_HEADER_STRUCT.size])
    return decode_packet_body(buf[PACKET_HEADER_STRUCT.size:PACKET_HEADER_STRUCT.size+body_size])
