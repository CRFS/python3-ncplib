from collections import namedtuple
from datetime import datetime, timedelta, timezone
from struct import Struct

from ncplib.errors import DecodeError
from ncplib.values import default_value_encoder, default_value_decoder


# Packet structs.

PACKET_HEADER_STRUCT = Struct("<4s4sIIIII4s")

FIELD_HEADER_STRUCT = Struct("<4s3sBI")

PARAM_HEADER_STRUCT = Struct("<4s3sB")

PACKET_FOOTER_STRUCT = Struct("<I4s")


# Packet constants.

PACKET_HEADER = b"\xdd\xcc\xbb\xaa"

PACKET_FOOTER = b"\xaa\xbb\xcc\xdd"


# u24 size encoding.

def encode_u24_size(value):
    return (value // 4).to_bytes(length=4, byteorder="little", signed=False)


# u24 size decoding.

def decode_u24_size(value):
    return int.from_bytes(value, byteorder="little", signed=False) * 4


# Param encoding.

def encode_params(params, value_encoder):
    buf = bytearray()
    for name, value in params.items():
        encoded_value = value_encoder.encode(value)
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

def decode_params(buf, offset, limit, value_decoder):
    while offset < limit:
        name, u24_size, type_id = PARAM_HEADER_STRUCT.unpack_from(buf, offset)
        size = decode_u24_size(u24_size)
        value_encoded = bytes(buf[offset+PARAM_HEADER_STRUCT.size:offset+size])
        value = value_decoder.decode(type_id, value_encoded)
        yield name, value
        offset += size
    if offset > limit:
        raise DecodeError("Parameter overflow by {} bytes".format(offset - limit))


# Field encoding.

Field = namedtuple("Field", ("name", "id", "params",))


def encode_fields(fields, value_encoder):
    buf = bytearray()
    for field in fields:
        encoded_params = encode_params(field.params, value_encoder)
        buf.extend(FIELD_HEADER_STRUCT.pack(
            field.name,
            encode_u24_size(FIELD_HEADER_STRUCT.size + len(encoded_params)),
            0,  # Field type ID is ignored.
            field.id,
        ))
        buf.extend(encoded_params)
    return buf


# Field decoding.

def decode_fields(buf, offset, limit, value_decoder):
    while offset < limit:
        name, u24_size, type_id, field_id = FIELD_HEADER_STRUCT.unpack_from(buf, offset)
        size = decode_u24_size(u24_size)
        params = dict(decode_params(buf, offset+FIELD_HEADER_STRUCT.size, offset+size, value_decoder))
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

def encode_packet(packet_type, packet_id, timestamp, info, fields, *, value_encoder=None):
    value_encoder = value_encoder or default_value_encoder
    encoded_fields = encode_fields(fields, value_encoder)
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

def decode_packet_cps(header_buf, *, value_decoder=None):
    value_decoder = value_decoder or default_value_decoder
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
    if header != PACKET_HEADER:
        raise DecodeError("Invalid packet header {}".format(header))
    timestamp = datetime.fromtimestamp(time, tz=timezone.utc) + timedelta(microseconds=nanotime // 1000)
    # Check the packet format.
    if format_id != PACKET_FORMAT_ID:
        raise DecodeError("Unknown packet format {}".format(format_id))
    # Decode the rest of the body data.
    size_remaining = size - PACKET_HEADER_STRUCT.size
    def decode_packet_body(body_buf):
        fields = list(decode_fields(body_buf, 0, size_remaining - PACKET_FOOTER_STRUCT.size, value_decoder))
        (
            checksum,
            footer,
        ) = PACKET_FOOTER_STRUCT.unpack_from(body_buf, size_remaining - PACKET_FOOTER_STRUCT.size)
        if footer != PACKET_FOOTER:
            raise DecodeError("Invalid packet footer {}".format(footer))
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


def decode_packet(buf, *, value_decoder=None):
    body_size, decode_packet_body = decode_packet_cps(buf[:PACKET_HEADER_STRUCT.size], value_decoder=value_decoder)
    return decode_packet_body(buf[PACKET_HEADER_STRUCT.size:PACKET_HEADER_STRUCT.size+body_size])
