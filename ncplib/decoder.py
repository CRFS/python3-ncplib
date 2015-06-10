import logging
from array import array
from collections import OrderedDict
from datetime import datetime, timezone, timedelta
from functools import partial

from ncplib.errors import DecodeError
from ncplib.constants import PACKET_HEADER_SIZE, PACKET_FIELD_HEADER_SIZE, PACKET_PARAM_HEADER_SIZE, PACKET_FOOTER_SIZE, PACKET_HEADER_HEADER, PACKET_FOOTER_HEADER, PacketFormat, ParamType
from ncplib.packets import Packet, RawParamValue


logger = logging.getLogger(__name__)


def _decode_uint(data):
    return int.from_bytes(data, "little", signed=False)


def _decode_int(data):
    return int.from_bytes(data, "little", signed=True)


def _decode_size(data):
    return _decode_uint(data) * 4


def _decode_str(data):
    return data.decode("latin1", errors="ignore")


def _decode_timestamp(data):
    seconds = _decode_uint(data[0:4])
    microseconds = _decode_uint(data[4:8]) / 1000
    return datetime.fromtimestamp(seconds, tz=timezone.utc) + timedelta(microseconds=microseconds)


_PARAM_VALUE_DECODERS = {
    ParamType.i32: _decode_int,
    ParamType.u32: _decode_uint,
    ParamType.string: _decode_str,
    ParamType.raw: bytes,
    ParamType.u8array: partial(array, "B"),
    ParamType.u16array: partial(array, "H"),
    ParamType.u32array: partial(array, "I"),
    ParamType.i8array: partial(array, "b"),
    ParamType.i16array: partial(array, "h"),
    ParamType.i32array: partial(array, "i"),
}


def _decode_param_value(param_value_data, param_type_id):
    param_value_data = bytes(param_value_data).split(b"\x00", 1)[0]  # Strip off any null bytes.
    # Look up the param type.
    try:
        param_type = ParamType(param_type_id)
    except ValueError:
        logger.warning("Not decoding param value %s (unknown type %s)", param_value_data, param_type_id)
        return RawParamValue(
            value = bytes(param_value_data),
            type_id = param_type,
        )
    # Decode the value data.
    logger.debug("Decoding param value %s (type %s)", param_value_data, param_type.name)
    param_value_decoder = _PARAM_VALUE_DECODERS[param_type]
    return param_value_decoder(param_value_data)


def _decode_param(param_data):
    param_name = bytes(param_data[:4])
    param_size = _decode_size(param_data[4:7])
    param_type_id = _decode_uint(param_data[7:8])
    logger.debug("Decoding param %s (%s bytes)", param_name, param_size)
    # Get the param data.
    param_value = _decode_param_value(param_data[PACKET_PARAM_HEADER_SIZE:param_size], param_type_id)
    # All done!
    return param_name, param_size, param_value


def _decode_field(field_data):
    field_name = bytes(field_data[:4])
    field_size = _decode_size(field_data[4:7])
    logger.debug("Decoding field %s (%s bytes)", field_name, field_size)
    # Unpack the params.
    params_read_position = PACKET_FIELD_HEADER_SIZE
    params = OrderedDict()
    while params_read_position < field_size:
        # Store the param data.
        param_name, param_size, param_value, = _decode_param(field_data[params_read_position:field_size])
        params[param_name] = param_value
        params_read_position += param_size
    if params_read_position != field_size:  # pragma: no cover
        raise DecodeError("Packet param overflow ({} bytes)".format(params_read_position - field_size))
    # All done!
    return field_name, field_size, params


def decode_packet(packet_data):
    if len(packet_data) < PACKET_HEADER_SIZE + PACKET_FOOTER_SIZE:
        raise DecodeError("Truncated packet")
    packet_data = memoryview(packet_data)
    # Decode the packet header.
    packet_header_header = packet_data[:4]  # pragma: no cover
    if packet_header_header != PACKET_HEADER_HEADER:
        raise DecodeError("Malformed packet header header {} (expected {})".format(packet_header_header, PACKET_HEADER_HEADER))
    packet_type = bytes(packet_data[4:8])
    packet_size = _decode_size(packet_data[8:12])
    packet_id = _decode_uint(packet_data[12:16])
    logger.debug("Decoding packet %s (%s bytes)", packet_type, packet_size)
    packet_format = _decode_uint(packet_data[16:20])
    if packet_format != PacketFormat.standard.value:
        logger.warning("Unknown packet format %s", packet_format)
    packet_timestamp = _decode_timestamp(packet_data[20:28])
    packet_info = bytes(packet_data[28:32])
    # Decode the footer.
    packet_footer_header = packet_data[-4:]
    if packet_footer_header != PACKET_FOOTER_HEADER:
        raise DecodeError("Malformed packet footer header {} (expected)".format(packet_footer_header, PACKET_FOOTER_HEADER))
    # Unpack all fields.
    field_read_position = PACKET_HEADER_SIZE
    field_end_position = packet_size - PACKET_FOOTER_SIZE
    fields = OrderedDict()
    while field_read_position < field_end_position:
        # Store the field data.
        field_name, field_size, field_params = _decode_field(packet_data[field_read_position:field_end_position])
        fields[field_name] = field_params
        field_read_position += field_size
    if field_read_position != field_end_position:  # pragma: no cover
        raise DecodeError("Packet field overflow ({} bytes)".format(field_read_position - field_end_position))
    # All done!
    packet_data.release()
    return Packet(
        type = packet_type,
        id = packet_id,
        timestamp = packet_timestamp,
        info = packet_info,
        fields = fields,
    )
