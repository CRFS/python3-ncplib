from ncplib.packets import encode_packet, decode_packet_cps, PACKET_HEADER_STRUCT


def write_packet(writer, packet_type, packet_id, timestamp, info, fields):
    encoded_packet = encode_packet(packet_type, packet_id, timestamp, info, fields)
    writer.write(encoded_packet)


async def read_packet(reader):
    header_buf = await reader.readexactly(PACKET_HEADER_STRUCT.size)
    size_remaining, decode_packet_body = decode_packet_cps(header_buf)
    body_buf = await reader.readexactly(size_remaining)
    return decode_packet_body(body_buf)
