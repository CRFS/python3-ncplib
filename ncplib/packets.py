from __future__ import annotations
from array import array
from datetime import datetime, timezone
from struct import Struct
from typing import Callable, Iterable, List, Tuple, Union
import warnings
from ncplib.errors import DecodeError, DecodeWarning
from ncplib.values import uint


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


# Packet encoding.

ARRAY_TYPE_CODES_TO_TYPE_ID = {
    "B": TYPE_ARRAY_U8,
    "H": TYPE_ARRAY_U16,
    "I": TYPE_ARRAY_U32,
    "b": TYPE_ARRAY_I8,
    "h": TYPE_ARRAY_I16,
    "i": TYPE_ARRAY_I32,
}


Bytes = Union[bytes, bytearray]
Param = Union[Bytes, str, int, uint, bool, array]
Params = Iterable[Tuple[str, Param]]
Fields = Iterable[Tuple[str, int, Params]]
Packet = Tuple[str, int, datetime, bytes, Fields]


def encode_packet(packet_type: str, packet_id: int, timestamp: datetime, info: bytes, fields: Fields) -> bytes:
    timestamp = timestamp.astimezone(timezone.utc)
    # Encode the header.
    packet_header = bytearray(PACKET_HEADER_SIZE)
    PACKET_HEADER_STRUCT.pack_into(
        packet_header, 0,
        PACKET_HEADER,  # Hardcoded packet header.
        packet_type.encode("latin1"),
        0,  # Placeholder for the packet size, which we will calculate soon.
        packet_id,
        PACKET_VERSION,
        int(timestamp.timestamp()), timestamp.microsecond * 1000,
        info,
    )
    chunks: List[Bytes] = [packet_header]
    offset = PACKET_HEADER_SIZE
    # Write the packet fields.
    for field_name, field_id, params in fields:
        field_offset = offset
        # Write the field header.
        field_header = bytearray(FIELD_HEADER_SIZE)
        FIELD_HEADER_STRUCT.pack_into(
            field_header, 0,
            field_name.encode("latin1"),
            b"\x00\x00\x00",  # Placeholder for the field size, which we will calculate soom.
            b"\x00",  # Field type ID is ignored.
            field_id,
        )
        chunks.append(field_header)
        offset += FIELD_HEADER_SIZE
        # Write the params.
        for param_name, param_value in params:
            if isinstance(param_value, uint):
                param_type_id = TYPE_U32
                param_value = param_value.to_bytes(4, "little")
            elif isinstance(param_value, (int, bool)):
                param_type_id = TYPE_I32
                param_value = param_value.to_bytes(4, "little", signed=True)
            elif isinstance(param_value, str):
                param_type_id = TYPE_STRING
                param_value = param_value.encode("utf-8") + b"\x00"
            elif isinstance(param_value, (bytes, bytearray, memoryview)):
                param_type_id = TYPE_RAW
            elif isinstance(param_value, array):
                param_type_id = ARRAY_TYPE_CODES_TO_TYPE_ID[param_value.typecode]
                param_value = param_value.tobytes()
            else:  # pragma: no cover
                raise TypeError(f"Unsupported value type {type(param_value)}")
            # Write the param header.
            param_size = PARAM_HEADER_SIZE + len(param_value)
            param_padding_size = -param_size % 4
            chunks.append(PARAM_HEADER_STRUCT.pack(
                param_name.encode("latin1"),
                ((param_size + param_padding_size) // 4).to_bytes(3, "little"),
                param_type_id,
            ))
            # Write the param value.
            chunks.append(param_value)
            chunks.append(b"\x00" * param_padding_size)
            offset += param_size + param_padding_size
        # Write the field size.
        field_header[4:7] = ((offset - field_offset) // 4).to_bytes(3, "little")[:3]
    # Encode the packet footer.
    chunks.append(PACKET_FOOTER_NO_CHECKSUM)
    # Write the packet size.
    packet_header[8:12] = ((offset + PACKET_FOOTER_SIZE) // 4).to_bytes(4, "little")
    # All done!
    return b"".join(chunks)


# PacketData decoding.

def decode_packet_cps(header_buf: Bytes) -> Tuple[int, Callable[[Bytes], Packet]]:
    (
        packet_header,
        packet_type,
        packet_size,
        packet_id,
        packet_format_id,
        packet_time,
        packet_nanotime,
        packet_info,
    ) = PACKET_HEADER_STRUCT.unpack(header_buf)
    packet_size = packet_size * 4
    if packet_header != PACKET_HEADER:  # pragma: no cover
        raise DecodeError(f"Invalid packet header {packet_header!r}")
    # Decode the rest of the body data.
    size_remaining = packet_size - PACKET_HEADER_SIZE

    def decode_packet_body(buf: Bytes) -> Packet:
        offset = 0
        # Check footer.
        if buf[-4:] != PACKET_FOOTER:  # pragma: no cover
            raise DecodeError(f"Invalid packet footer {buf[-4:]!r}")
        # Decode fields.
        field_limit = size_remaining - PACKET_FOOTER_SIZE
        fields = []
        while offset < field_limit:
            # Decode field header.
            field_name, field_size, field_type_id, field_id = FIELD_HEADER_STRUCT.unpack_from(buf, offset)
            param_limit = offset + int.from_bytes(field_size, "little") * 4
            offset += FIELD_HEADER_SIZE
            # Decode params.
            params = []
            while offset < param_limit:
                # Decode the param header.
                param_name, param_size, param_type_id = PARAM_HEADER_STRUCT.unpack_from(buf, offset)
                param_size = int.from_bytes(param_size, "little") * 4
                # Decode the param value.
                param_value_raw = buf[offset+PARAM_HEADER_SIZE:offset+param_size]
                param_value: Param
                if param_type_id == TYPE_U32:
                    param_value = uint.from_bytes(param_value_raw, "little")
                elif param_type_id == TYPE_I32:
                    param_value = int.from_bytes(param_value_raw, "little", signed=True)
                elif param_type_id == TYPE_STRING:
                    param_value = param_value_raw.split(b"\x00", 1)[0].decode()
                elif param_type_id == TYPE_RAW:
                    param_value = bytes(param_value_raw)
                elif param_type_id == TYPE_ARRAY_U8:
                    param_value = array("B", param_value_raw)
                elif param_type_id == TYPE_ARRAY_U16:
                    param_value = array("H", param_value_raw)
                elif param_type_id == TYPE_ARRAY_U32:
                    param_value = array("I", param_value_raw)
                elif param_type_id == TYPE_ARRAY_I8:
                    param_value = array("b", param_value_raw)
                elif param_type_id == TYPE_ARRAY_I16:
                    param_value = array("h", param_value_raw)
                elif param_type_id == TYPE_ARRAY_I32:
                    param_value = array("i", param_value_raw)
                else:  # pragma: no cover
                    warnings.warn(DecodeWarning("Unsupported type ID", param_type_id))
                # Store the param.
                params.append((param_name.rstrip(b" \x00").decode("latin1"), param_value))
                offset += param_size
                # Check for param overflow.
                if offset > param_limit:  # pragma: no cover
                    raise DecodeError(f"Parameter overflow by {offset - param_limit} bytes")
            # Store the field.
            fields.append((field_name.rstrip(b" \x00").decode("latin1"), field_id, params))
        # Check for field overflow.
        if offset > field_limit:  # pragma: no cover
            raise DecodeError(f"Field overflow by {offset - field_limit} bytes")
        # All done!
        return (
            packet_type.rstrip(b" \x00").decode("latin1"),
            packet_id,
            datetime.fromtimestamp(packet_time, tz=timezone.utc).replace(microsecond=packet_nanotime // 1000),
            packet_info,
            fields,
        )

    # Return the number of bytes to read, and the function to finish decoding.
    return size_remaining, decode_packet_body


def decode_packet(buf: Bytes) -> Packet:
    body_size, decode_packet_body = decode_packet_cps(buf[:PACKET_HEADER_SIZE])
    return decode_packet_body(buf[PACKET_HEADER_SIZE:])  # 32 is the size of the packet header.
