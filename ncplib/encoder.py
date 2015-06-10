import sys
from array import array
from functools import partial
from collections.abc import Mapping
from math import ceil
from datetime import datetime, timezone

from ncplib.constants import PACKET_HEADER_SIZE, PACKET_FIELD_HEADER_SIZE, PACKET_PARAM_HEADER_SIZE, PACKET_FOOTER_SIZE, PACKET_HEADER_HEADER, PACKET_FOOTER_HEADER, PacketFormat, ParamType
from ncplib.packets import RawParamValue


# Type checking.

def _require_type(name, value, type, type_desc=None):  # pragma: no cover
    if not isinstance(value, type):
        raise TypeError("{} '{}' should be of type {}".format(name, value, type_desc or type.__name__))


_require_bytes = partial(_require_type, type=(bytes, bytearray, memoryview), type_desc="bytes")


_require_int = partial(_require_type, type=int)


def _require_key(name, value):  # pragma: no cover
    _require_bytes(name, value)
    if len(value) != 4:
        raise ValueError("{} '{}' should be a four-byte value".format(name, value))


def _require_timestamp(name, value):  # pragma: no cover
    _require_type(name, value, datetime)
    if value.tzinfo is None:
        raise ValueError("{} '{}' should be timezone-aware".format(name, value))


# Param serialization.

def _serialize_param_value_raw(param_value):
    _require_bytes("Raw param value", param_value.value)
    _require_int("Raw param type ID", param_value.type_id)
    return param_value.type_id, param_value.value


def _serialize_param_value_int(param_value):
    return ParamType.i32.value, param_value.to_bytes(4, "little", signed=True)


def _serialize_param_value_str(param_value):
    return ParamType.string.value, param_value.encode("latin1", errors="ignore") + b"\x00"


def _serialize_param_value_bytes(param_value):
    return ParamType.raw.value, param_value


_PARAM_VALUE_ARRAY_TYPES = {
    "B": ParamType.u8array,
    "H": ParamType.u16array,
    "I": ParamType.u32array,
    "b": ParamType.i8array,
    "h": ParamType.i16array,
    "i": ParamType.i32array,
}


def _serialize_param_value_array(param_value):
    try:
        param_type = _PARAM_VALUE_ARRAY_TYPES[param_value.typecode]
    except KeyError:  # pragma: no cover
        raise TypeError("Unsupported param value type (array[{}])".format(param_value.typecode))
    # Convert the value to bytes.
    if sys.byteorder == "big":
        param_value = param_value[:].byteswap()
    # All done!
    return param_type.value, param_value.tobytes()


_PARAM_VALUE_SERIALIZERS = {
    RawParamValue: _serialize_param_value_raw,
    int: _serialize_param_value_int,
    str: _serialize_param_value_str,
    bytes: _serialize_param_value_bytes,
    bytearray: _serialize_param_value_bytes,
    memoryview: _serialize_param_value_bytes,
    array: _serialize_param_value_array,
}


def _serialize_param_value(param_value):
    try:
        param_value_serializer = _PARAM_VALUE_SERIALIZERS[type(param_value)]
    except KeyError:  # pragma: no cover
        raise TypeError("Unsupported param value type ({})".format(type(param_value).__name__))
    param_type_id, serialized_param_value = param_value_serializer(param_value)
    param_size = int(ceil((PACKET_PARAM_HEADER_SIZE + len(serialized_param_value)) / 4) * 4)  # Round up size to nearest 4 bytes.
    return param_size, param_type_id, serialized_param_value


# Encoders.

def _encode_uint(buf, value):
    buf[:] = value.to_bytes(len(buf), "little", signed=False)


def _encode_size(buf, value):
    _encode_uint(buf, int(value / 4))


def _encode_timestamp(buf, value):
    value = value.astimezone(timezone.utc)
    _encode_uint(buf[:4], int(value.timestamp()))
    _encode_uint(buf[4:8], value.microsecond * 1000)


def _encode_param(buf, param_name, param_size, param_type_id, serialized_param_value):
    _require_key("Param name", param_name)
    buf[:4] = param_name
    _encode_size(buf[4:7], param_size)
    _encode_uint(buf[7:8], param_type_id)
    buf[8:8+len(serialized_param_value)] = serialized_param_value


def _encode_field(buf, field_name, field_size, field_id, serialized_params):
    _require_key("Field name", field_name)
    buf[:4] = field_name
    _encode_size(buf[4:7], field_size)
    _encode_uint(buf[8:12], field_id)
    # Encode the params.
    field_write_position = PACKET_FIELD_HEADER_SIZE
    for param_name, param_size, param_type_id, serialized_param_value in serialized_params:
        _encode_param(buf[field_write_position:field_write_position+param_size], param_name, param_size, param_type_id, serialized_param_value)
        field_write_position += param_size


def encode_packet(packet_type, packet_id, packet_timestamp, packet_info, packet_fields):
    _require_key("Packet type", packet_type)
    _require_int("Packet ID", packet_id)
    _require_timestamp("Packet timestamp", packet_timestamp)
    _require_key("Packet info", packet_info)
    _require_type("Packet fields", packet_fields, Mapping)
    # Serialize the param values.
    packet_size = PACKET_HEADER_SIZE + PACKET_FOOTER_SIZE
    serialized_fields = []
    for field_name, params in packet_fields.items():
        field_size = PACKET_FIELD_HEADER_SIZE
        serialized_params = []
        for param_name, param_value in params.items():
            param_size, param_type_id, serialized_param_value = _serialize_param_value(param_value)
            serialized_params.append((param_name, param_size, param_type_id, serialized_param_value))
            field_size += param_size
        serialized_fields.append((field_name, field_size, serialized_params))
        packet_size += field_size
    # Create a buffer for the packet.
    packet_data = bytearray(packet_size)
    buf = memoryview(packet_data)
    # Encode the header.
    buf[:4] = PACKET_HEADER_HEADER
    buf[4:8] = packet_type
    _encode_size(buf[8:12], packet_size)
    _encode_uint(buf[12:16], packet_id)
    _encode_uint(buf[16:20], PacketFormat.standard.value)
    _encode_timestamp(buf[20:28], packet_timestamp)
    buf[28:32] = packet_info
    # Encode the fields.
    field_write_position = PACKET_HEADER_SIZE
    for field_id, serialized_field in enumerate(serialized_fields):
        field_name, field_size, serialized_params = serialized_field
        _encode_field(buf[field_write_position:field_write_position+field_size], field_name, field_size, field_id, serialized_params)
        field_write_position += field_size
    # Encode the footer.
    buf[-4:] = PACKET_FOOTER_HEADER
    # All done!
    buf.release()
    return packet_data
