import sys
from array import array
from collections.abc import Mapping
from math import ceil
from datetime import datetime, timezone

from ncplib.constants import PACKET_HEADER_SIZE, PACKET_FIELD_HEADER_SIZE, PACKET_PARAM_HEADER_SIZE, PACKET_FOOTER_SIZE, PACKET_HEADER_HEADER, PACKET_FOOTER_HEADER, PacketFormat, ParamType
from ncplib.packets import Packet, RawParamValue


# Type checking.

def _is_bytes(value):
    return isinstance(value, (bytes, bytearray, memoryview))


def _is_key(value):
    return _is_bytes(value) and len(value) == 4


# Param serialization.

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
    except KeyError:
        raise TypeError("Unsupported param value type (array[{}])".format(param_value.typecode))
    # Convert the value to bytes.
    if sys.byteorder == "big":
        param_value = param_value[:].byteswap()
    # All done!
    return param_value.tobytes(), param_type.value


def _serialize_param_value(param_value):
    if isinstance(param_value, RawParamValue):
        return param_value
    if isinstance(param_value, int):
        return param_value.to_bytes(4, "little", signed=True), ParamType.i32.value,
    if isinstance(param_value, str):
        return param_value.encode("latin1", errors="ignore") + b"\x00", ParamType.string.value
    if _is_bytes(param_value):
        return param_value, ParamType.raw.value
    if isinstance(param_value, array):
        return _serialize_param_value_array(param_value)
    raise TypeError("Unsupported param value type ({})".format(type(param_value)))


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
    assert _is_key(param_name), "Param name should be a 4 byte key"
    buf[:4] = param_name
    _encode_size(buf[4:7], param_size)
    _encode_uint(buf[7:8], param_type_id)
    buf[8:8+len(serialized_param_value)] = serialized_param_value


def _encode_field(buf, field_name, field_size, field_id, serialized_params):
    assert _is_key(field_name), "Field name should be a 4 byte key"
    buf[:4] = field_name
    _encode_size(buf[4:7], field_size)
    _encode_uint(buf[8:12], field_id)
    # Encode the params.
    field_write_position = PACKET_FIELD_HEADER_SIZE
    for param_name, param_size, param_type_id, serialized_param_value in serialized_params:
        _encode_param(buf[field_write_position:field_write_position+param_size], param_name, param_size, param_type_id, serialized_param_value)
        field_write_position += param_size


def encode_packet(packet):
    assert isinstance(packet, Packet)
    assert _is_key(packet.type), "Packet type should be a 4 byte key"
    assert isinstance(packet.id, int), "Packet ID should be an int"
    assert isinstance(packet.timestamp, datetime) and packet.timestamp.tzinfo is not None, "Packet timestamp should be a timezone-aware datetime"
    assert _is_key(packet.info), "Packet info should be a 4 byte value"
    assert isinstance(packet.fields, Mapping), "Packet fields should be a Mapping"
    # Serialize the param values.
    packet_size = PACKET_HEADER_SIZE + PACKET_FOOTER_SIZE
    serialized_fields = []
    for field_name, params in packet.fields.items():
        field_size = PACKET_FIELD_HEADER_SIZE
        serialized_params = []
        for param_name, param_value in params.items():
            serialized_param_value, param_type_id = _serialize_param_value(param_value)
            param_size = int(ceil((PACKET_PARAM_HEADER_SIZE + len(serialized_param_value)) / 4) * 4)  # Round up size to nearest 4 bytes.
            serialized_params.append((param_name, param_size, param_type_id, serialized_param_value))
            field_size += param_size
        serialized_fields.append((field_name, serialized_params, field_size))
        packet_size += field_size
    # Create a buffer for the packet.
    packet_data = bytearray(packet_size)
    buf = memoryview(packet_data)
    # Encode the header.
    buf[:4] = PACKET_HEADER_HEADER
    buf[4:8] = packet.type
    _encode_size(buf[8:12], packet_size)
    _encode_uint(buf[12:16], packet.id)
    _encode_uint(buf[16:20], PacketFormat.standard.value)
    _encode_timestamp(buf[20:28], packet.timestamp)
    buf[28:32] = packet.info
    # Encode the fields.
    field_write_position = PACKET_HEADER_SIZE
    for field_id, serialized_field in enumerate(serialized_fields):
        field_name, serialized_params, field_size = serialized_field
        _encode_field(buf[field_write_position:field_write_position+field_size], field_name, field_size, field_id, serialized_params)
        field_write_position += field_size
    # Encode the footer.
    buf[-4:] = PACKET_FOOTER_HEADER
    # All done!
    buf.release()
    return packet_data
