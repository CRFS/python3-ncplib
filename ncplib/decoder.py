import asyncio, logging
from datetime import datetime

from ncplib import structs
from ncplib.errors import PacketError
from ncplib.types import ParamType
from ncplib.packets import Packet


logger = logging.getLogger(__name__)


# Bytes decoder routines.

def _decode_int24(value):
    return int.from_bytes(value, "little")


def _decode_str(value):
    return value.decode("latin1", errors="ignore")


def _decode_null_terminated_str(value):
    # Split off null termination.
    value = value.split(b"\x00", 1)[0]
    # Convert to unicode.
    value = _decode_str(value)
    # All done!
    return value


DATA_TYPES = {
    ParamType.string.value: _decode_null_terminated_str
}


# StreamReader decoder routines.

@asyncio.coroutine
def _decode_bytes(reader, size):
    return (yield from reader.readexactly(size))


@asyncio.coroutine
def _decode_struct(reader, struct):
    data = yield from _decode_bytes(reader, struct.size)
    result = struct.unpack(data)
    return result


@asyncio.coroutine
def _decode_param_value(reader, param_size, param_type):
    param_value = yield from _decode_bytes(reader, param_size - structs.PARAM_STRUCT.size)
    # Decode the value type.
    try:
        value_decoder = DATA_TYPES[param_type]
    except KeyError:  # pragma: no cover
        logger.warning("Not decoding param value %s (unknown type %s)", param_value, param_type)
    else:
        logger.debug("Decoding param value %s (type %s)", param_value, ParamType(param_type).name)
        param_value = value_decoder(param_value)
    # All done!
    return param_value


@asyncio.coroutine
def _decode_param(reader):
    (
        param_name,
        param_size,
        param_type,
    ) = yield from _decode_struct(reader, structs.PARAM_STRUCT)
    param_name = _decode_str(param_name)
    # Decode the param size as a 3 byte integer, and convert from units of 32bit words to bytes.
    param_size = _decode_int24(param_size) * 4
    logger.debug("Decoding param %s (%s bytes)", param_name, param_size)
    # Get the param data.
    param_value = yield from _decode_param_value(reader, param_size, param_type)
    # All done!
    return param_name, param_size, param_value


@asyncio.coroutine
def _decode_field(reader):
    (
        field_name,
        field_size,
        field_type,
        field_id,
    ) = yield from _decode_struct(reader, structs.FIELD_STRUCT)
    field_name = _decode_str(field_name)
    # Decode the field size as a 3 byte integer, and convert from units of 32bit words to bytes.
    field_size = _decode_int24(field_size) * 4
    logger.debug("Decoding field %s (%s bytes)", field_name, field_size)
    # Unpack the params.
    params_bytes_remaining = field_size - structs.FIELD_STRUCT.size
    params = {}
    while params_bytes_remaining > 0:
        # Store the param data.
        param_name, param_size, param_value, = yield from _decode_param(reader)
        params[param_name] = param_value
        params_bytes_remaining -= param_size
    if params_bytes_remaining != 0:  # pragma: no cover
        raise PacketError("Packet params overflowed by {} bytes".format(-params_bytes_remaining))
    # All done!
    return field_name, field_size, params


@asyncio.coroutine
def decode_packet(reader):
    # Unpack the header.
    (
        packet_header,
        packet_type,
        packet_size,
        packet_id,
        packet_format,
        packet_time,
        packet_nanotime,
        packet_info,
    ) = yield from _decode_struct(reader, structs.HEADER_STRUCT)
    packet_type = _decode_str(packet_type)
    packet_time = float(packet_time)
    packet_nanotime = float(packet_nanotime)
    packet_timestamp = datetime.fromtimestamp(packet_time + (packet_nanotime / 1000000000))
    if packet_format != 1:  # pragma: no cover
        raise PacketError("Unknown packet format {}".format(packet_format))
    # Convert the packet size from units of 32bit words to bytes.
    packet_size *= 4
    logger.debug("Decoding packet %s (%s bytes)", packet_type, packet_size)
    # Unpack all fields.
    fields_bytes_remaining = packet_size - structs.HEADER_STRUCT.size - structs.FOOTER_STRUCT.size
    fields = {}
    while fields_bytes_remaining > 0:
        # Store the field data.
        field_name, field_size, field_params = yield from _decode_field(reader)
        fields[field_name] = field_params
        fields_bytes_remaining -= field_size
    if fields_bytes_remaining != 0:  # pragma: no cover
        raise PacketError("Packet fields overflowed by {} bytes".format(-fields_bytes_remaining))
    # Unpack the footer.
    (
        packet_checksum,
        packet_footer,
    ) = yield from _decode_struct(reader, structs.FOOTER_STRUCT)
    if packet_footer[::-1] != packet_header:  # pragma: no cover
        raise PacketError("Corrupt packet footer, expected {}, received {}".format(packet_header, packet_footer))
    # All done!
    return Packet(
        type = packet_type,
        id = packet_id,
        timestamp = packet_timestamp,
        fields = fields,
    )
