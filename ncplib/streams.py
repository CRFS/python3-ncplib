import asyncio

from ncplib.errors import NetworkError
from ncplib.encoding import encode_packet, decode_packet_cps, PACKET_HEADER_STRUCT


def write_packet(writer, packet_type, packet_id, timestamp, info, fields):
    encoded_packet = encode_packet(packet_type, packet_id, timestamp, info, fields)
    try:
        writer.write(encoded_packet)
    except (OSError, EOFError) as ex:
        raise NetworkError from ex


@asyncio.coroutine
def read_packet(reader):
    try:
        header_buf = yield from reader.readexactly(PACKET_HEADER_STRUCT.size)
        size_remaining, decode_packet_body = decode_packet_cps(header_buf)
        body_buf = yield from reader.readexactly(size_remaining)
        return decode_packet_body(body_buf)
    except (OSError, EOFError) as ex:
        raise NetworkError from ex
