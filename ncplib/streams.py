import asyncio

from ncplib.errors import wrap_network_errors
from ncplib.encoding import encode_packet, decode_packet_cps, PACKET_HEADER_STRUCT


def write_packet(writer, packet_type, packet_id, timestamp, info, fields, *, value_encoder=None):
    encoded_packet = encode_packet(packet_type, packet_id, timestamp, info, fields, value_encoder=value_encoder)
    with wrap_network_errors():
        writer.write(encoded_packet)


@asyncio.coroutine
def read_packet(reader, *, value_decoder=None):
    with wrap_network_errors():
        header_buf = yield from reader.readexactly(PACKET_HEADER_STRUCT.size)
        size_remaining, decode_packet_body = decode_packet_cps(header_buf, value_decoder=value_decoder)
        body_buf = yield from reader.readexactly(size_remaining)
        return decode_packet_body(body_buf)
