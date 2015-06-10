from collections.abc import Mapping
from itertools import starmap
from datetime import datetime

from ncplib.structs import HEADER_STRUCT, FIELD_STRUCT, PARAM_STRUCT, FOOTER_STRUCT
from ncplib.constants import PacketFormat, ParamType


def _encode_int24(value):
    return value.to_bytes(3, "little")


def _encode_size(value):
    return int(value / 4)  # Convert from units of bytes to 32bit words.


def _encode_str(value):
    return value.encode("latin1", errors="ignore")


def _encode_null_terminated_str(value):
    # Convert to bytes.
    value = _encode_str(value)
    # Add however many remaining null-terminated strings are required to make the length a multiple of 4.
    value += b"\x00" * (4 - (len(value) % 4))
    # All done!
    return value


def _encode_param_value(value):
    if isinstance(value, str):
        return _encode_null_terminated_str(value), ParamType.string
    else:
        assert False


def _encode_param(name, value):
    assert isinstance(name, str) and len(name) == 4
    encoded_param_value, param_type = _encode_param_value(value)
    encoded_param = PARAM_STRUCT.pack(
        _encode_str(name),
        _encode_int24(_encode_size(len(encoded_param_value) + PARAM_STRUCT.size)),
        param_type.value,
    )
    return encoded_param + encoded_param_value


def _encode_field(id, field):
    name, params = field
    assert isinstance(name, str) and len(name) == 4
    assert isinstance(params, Mapping)
    encoded_params = b"".join(starmap(_encode_param, params.items()))
    encoded_field = FIELD_STRUCT.pack(
        _encode_str(name),
        _encode_int24(_encode_size(len(encoded_params) + FIELD_STRUCT.size)),
        0,  # Magic field type,
        id,
    )
    # All done!
    return encoded_field + encoded_params


def encode_packet(type, id, timestamp, fields):
    assert isinstance(type, str) and len(type) == 4
    assert isinstance(id, int)
    assert isinstance(timestamp, datetime) and timestamp.tzinfo is not None
    assert isinstance(fields, Mapping)
    # Write the footer.
    encoded_footer = FOOTER_STRUCT.pack(
        0,  # No checksum,
        b'\xaa\xbb\xcc\xdd',  # Magic packet footer.
    )
    # Write all the fields.
    encoded_fields = b"".join(starmap(_encode_field, enumerate(fields.items())))
    # Write the header.
    encoded_header = HEADER_STRUCT.pack(
        b'\xdd\xcc\xbb\xaa',  # Magic packet header.
        _encode_str(type),
        _encode_size(FOOTER_STRUCT.size + len(encoded_fields) + HEADER_STRUCT.size),
        id,
        PacketFormat.standard.value,
        int(timestamp.timestamp()),
        int(timestamp.microsecond * 1000),
        b'\x00\x00\x00\x00',  # Packet info, must be blank.
    )
    # All done!
    return encoded_header + encoded_fields + encoded_footer
