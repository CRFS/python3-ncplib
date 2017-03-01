import warnings
from struct import Struct
from ncplib.errors import DecodeError, DecodeWarning
from ncplib.helpers import unix_to_datetime, datetime_to_unix
from ncplib.values import encode_value, decode_value


# Packet structs.

PACKET_HEADER_STRUCT = Struct("<4s4sII4sII4s")

FIELD_HEADER_STRUCT = Struct("<4s3s1sI")

PARAM_HEADER_STRUCT = Struct("<4s3sB")


# Sizes.

PACKET_HEADER_SIZE = PACKET_HEADER_STRUCT.size

FIELD_HEADER_SIZE = FIELD_HEADER_STRUCT.size

PARAM_HEADER_SIZE = PARAM_HEADER_STRUCT.size

PACKET_FOOTER_SIZE = 8


# Byte sequences.

PACKET_HEADER = b"\xdd\xcc\xbb\xaa"

PACKET_VERSION = (1).to_bytes(4, "little", signed=False)

PACKET_FOOTER = b"\xaa\xbb\xcc\xdd"

PACKET_FOOTER_NO_CHECKSUM = b"\x00\x00\x00\x00" + PACKET_FOOTER


# Packet encoding.

def encode_packet(packet_type, packet_id, timestamp, info, fields):
    timestamp_unix, timestamp_nano = datetime_to_unix(timestamp)
    # Encode the header.
    buf = bytearray(PACKET_HEADER_SIZE)
    PACKET_HEADER_STRUCT.pack_into(
        buf, 0,
        PACKET_HEADER,  # Hardcoded packet header.
        packet_type.encode("latin1"),
        0,  # Placeholder for the packet size, which we will calculate soon.
        packet_id,
        PACKET_VERSION,
        timestamp_unix, timestamp_nano,
        info,
    )
    offset = PACKET_HEADER_SIZE
    # Write the packet fields.
    for field_name, field_id, params in fields:
        field_offset = offset
        # Write the field header.
        buf.extend(FIELD_HEADER_STRUCT.pack(
            field_name.encode("latin1"),
            b"\x00\x00\x00",  # Placeholder for the field size, which we will calculate soom.
            b"\x00",  # Field type ID is ignored.
            field_id,
        ))
        offset += FIELD_HEADER_SIZE
        # Write the params.
        for param_name, param_value in params.items():
            # Encode the param value.
            param_type_id, param_encoded_value = encode_value(param_value)
            # Write the param header.
            param_size = PARAM_HEADER_SIZE + len(param_encoded_value)
            param_padding_size = -param_size % 4
            buf.extend(PARAM_HEADER_STRUCT.pack(
                param_name.encode("latin1"),
                ((param_size + param_padding_size) // 4).to_bytes(3, "little"),
                param_type_id,
            ))
            # Write the param value.
            buf.extend(param_encoded_value)
            buf.extend(b"\x00" * param_padding_size)
            offset += param_size + param_padding_size
        # Write the field size.
        buf[field_offset+4:field_offset+7] = ((offset - field_offset) // 4).to_bytes(3, "little")[:3]
    # Encode the packet footer.
    buf.extend(PACKET_FOOTER_NO_CHECKSUM)
    # Write the packet size.
    buf[8:12] = ((offset + PACKET_FOOTER_SIZE) // 4).to_bytes(4, "little")
    # All done!
    return buf


# PacketData decoding.

def decode_packet_cps(header_buf):
    (
        header,
        packet_type,
        size,
        packet_id,
        format_id,
        time,
        nanotime,
        info,
    ) = PACKET_HEADER_STRUCT.unpack(header_buf)
    size = size * 4
    if header != PACKET_HEADER:  # pragma: no cover
        raise DecodeError("Invalid packet header {}".format(header))
    # Decode the rest of the body data.
    size_remaining = size - PACKET_HEADER_SIZE

    def decode_packet_body(buf):
        offset = 0
        # Check footer.
        if buf[-4:] != PACKET_FOOTER:  # pragma: no cover
            raise DecodeError("Invalid packet footer {}".format(buf[-4:]))
        # Decode fields.
        field_limit = size_remaining - PACKET_FOOTER_SIZE
        fields = []
        while offset < field_limit:
            # Decode field header.
            field_name, field_size, field_type_id, field_id = FIELD_HEADER_STRUCT.unpack_from(buf, offset)
            param_limit = offset + int.from_bytes(field_size, "little") * 4
            offset += FIELD_HEADER_SIZE
            # Decode params.
            params = {}
            while offset < param_limit:
                # HACK: Work around a known garbled NCP packet problem from Axis nodes.
                if buf[offset:offset+8] == PACKET_FOOTER_NO_CHECKSUM:
                    warnings.warn(DecodeWarning("Encountered embedded packet footer bug"))
                    offset += 8
                    continue
                # Decode the param header.
                param_name, param_size, param_type_id = PARAM_HEADER_STRUCT.unpack_from(buf, offset)
                param_size = int.from_bytes(param_size, "little") * 4
                # Decode the param value.
                param_value_encoded = bytes(buf[offset+PARAM_HEADER_SIZE:offset+param_size])
                params[param_name.rstrip(b" \x00").decode("latin1")] = decode_value(param_type_id, param_value_encoded)
                offset += param_size
                # Check for param overflow.
                if offset > param_limit:  # pragma: no cover
                    raise DecodeError("Parameter overflow by {} bytes".format(offset - param_limit))
            # Store the field.
            fields.append((field_name.rstrip(b" \x00").decode("latin1"), field_id, params))
        # Check for field overflow.
        if offset > field_limit:  # pragma: no cover
            raise DecodeError("Field overflow by {} bytes".format(offset - field_limit))

        # All done!
        return (
            packet_type.rstrip(b" \x00").decode("latin1"),
            packet_id,
            unix_to_datetime(time, nanotime),
            info,
            fields,
        )

    # Return the number of bytes to read, and the function to finish decoding.
    return size_remaining, decode_packet_body


def decode_packet(buf):
    body_size, decode_packet_body = decode_packet_cps(buf[:PACKET_HEADER_SIZE])
    return decode_packet_body(buf[PACKET_HEADER_SIZE:])  # 32 is the size of the packet header.
