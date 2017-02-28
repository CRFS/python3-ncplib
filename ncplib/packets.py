import warnings
from collections import namedtuple, OrderedDict
from struct import Struct
from ncplib.errors import DecodeError, DecodeWarning
from ncplib.helpers import unix_to_datetime, datetime_to_unix
from ncplib.values import encode_value, decode_value


# Packet structs.

PACKET_HEADER_STRUCT = Struct("<4s4sII4sII4s")

FIELD_HEADER_STRUCT = Struct("<4s3s1sI")

PARAM_HEADER_STRUCT = Struct("<4s3sB")

PACKET_FOOTER_STRUCT = Struct("<I4s")


# Identifier encoding.

def encode_identifier(value):
    return value.encode("latin1").ljust(4, b" ")


# Identifier decoding.

def decode_identifier(value):
    return value.rstrip(b" \x00").decode("latin1")


# u24 size decoding.

def decode_u24_size(value):
    return int.from_bytes(value, "little") * 4


# Param decoding.

def decode_params(buf, offset, limit):
    while offset < limit:
        # HACK: Work around a known garbled NCP packet problem from Axis nodes.
        if buf[offset:offset+8] == b"\x00\x00\x00\x00\xaa\xbb\xcc\xdd":
            warnings.warn(DecodeWarning("Encountered embedded packet footer bug"))
            offset += 8
            continue
        # Keep decoding.
        name, u24_size, type_id = PARAM_HEADER_STRUCT.unpack_from(buf, offset)
        name = decode_identifier(name)
        size = decode_u24_size(u24_size)
        value_encoded = bytes(buf[offset+PARAM_HEADER_STRUCT.size:offset+size])
        value = decode_value(type_id, value_encoded)
        yield name, value
        offset += size
    if offset > limit:  # pragma: no cover
        raise DecodeError("Parameter overflow by {} bytes".format(offset - limit))


# Field decoding.

FieldData = namedtuple("FieldData", ("name", "id", "params",))


def decode_fields(buf, offset, limit):
    while offset < limit:
        name, u24_size, type_id, field_id = FIELD_HEADER_STRUCT.unpack_from(buf, offset)
        name = decode_identifier(name)
        size = decode_u24_size(u24_size)
        params = OrderedDict(decode_params(buf, offset+FIELD_HEADER_STRUCT.size, offset+size))
        yield FieldData(
            name=name,
            id=field_id,
            params=params,
        )
        offset += size
    if offset > limit:  # pragma: no cover
        raise DecodeError("Field overflow by {} bytes".format(offset - limit))


# Packet encoding.

def encode_packet(packet_type, packet_id, timestamp, info, fields):
    timestamp_unix, timestamp_nano = datetime_to_unix(timestamp)
    # Encode the header.
    buf = bytearray(32)  # 32 is the size of the packet header.
    PACKET_HEADER_STRUCT.pack_into(
        buf, 0,
        b"\xdd\xcc\xbb\xaa",  # Hardcoded packet header.
        encode_identifier(packet_type),
        0,  # Placeholder for the packet size, which we will calculate soon.
        packet_id,
        b'\x01\x00\x00\x00',
        timestamp_unix, timestamp_nano,
        info,
    )
    # Write the packet fields.
    offset = 32  # 32 is the size of the packet header.
    for field_name, field_id, params in fields:
        field_offset = offset
        # Write the field header.
        buf.extend(FIELD_HEADER_STRUCT.pack(
            encode_identifier(field_name),
            b"\x00\x00\x00",  # Placeholder for the field size, which we will calculate soom.
            b"\x00",  # Field type ID is ignored.
            field_id,
        ))
        # Write the params.
        offset += 12  # 12 is the size of the field header.
        for param_name, param_value in params.items():
            # Encode the param value.
            param_type_id, param_encoded_value = encode_value(param_value)
            # Write the param header.
            param_size = 8 + len(param_encoded_value)  # 8 is the size of the param header.
            param_padding_size = -param_size % 4
            buf.extend(PARAM_HEADER_STRUCT.pack(
                encode_identifier(param_name),
                ((param_size + param_padding_size) // 4).to_bytes(3, "little"),
                param_type_id,
            ))
            # Write the param value.
            buf.extend(param_encoded_value)
            buf.extend(b"\x00" * param_padding_size)
            # Keep track of field size.
            offset += param_size + param_padding_size
        # Write the field size.
        buf[field_offset+4:field_offset+7] = ((offset - field_offset) // 4).to_bytes(3, "little")[:3]
    # Encode the packet footer.
    buf.extend(b"\x00\x00\x00\x00\xaa\xbb\xcc\xdd")  # Hardcoded packet footer with no checksum.
    # Write the packet size.
    buf[8:12] = ((offset + 8) // 4).to_bytes(4, "little")  # 8 is the size of the packet footer.
    # All done!
    return buf


# PacketData decoding.

PacketData = namedtuple("PacketData", ("type", "id", "timestamp", "info", "fields",))


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
    packet_type = decode_identifier(packet_type)
    size = size_words * 4
    if header != b"\xdd\xcc\xbb\xaa":  # pragma: no cover
        raise DecodeError("Invalid packet header {}".format(header))
    timestamp = unix_to_datetime(time, nanotime)
    # Decode the rest of the body data.
    size_remaining = size - PACKET_HEADER_STRUCT.size

    def decode_packet_body(body_buf):
        if len(body_buf) > size_remaining:  # pragma: no cover
            raise DecodeError("Packet body overflow by {} bytes".format(len(body_buf) - size_remaining))
        fields = list(decode_fields(body_buf, 0, size_remaining - PACKET_FOOTER_STRUCT.size))
        (
            checksum,
            footer,
        ) = PACKET_FOOTER_STRUCT.unpack_from(body_buf, size_remaining - PACKET_FOOTER_STRUCT.size)
        if footer != b"\xaa\xbb\xcc\xdd":  # pragma: no cover
            raise DecodeError("Invalid packet footer {}".format(footer))
        # All done!
        return PacketData(
            type=packet_type,
            id=packet_id,
            timestamp=timestamp,
            info=info,
            fields=fields,
        )

    # Return the number of bytes to read, and the function to finish decoding.
    return size_remaining, decode_packet_body


def decode_packet(buf):
    body_size, decode_packet_body = decode_packet_cps(buf[:PACKET_HEADER_STRUCT.size])
    return decode_packet_body(buf[PACKET_HEADER_STRUCT.size:])
