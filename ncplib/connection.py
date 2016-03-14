import asyncio
from datetime import datetime, timezone
from uuid import getnode as get_mac
from ncplib.packets import Field, encode_packet, decode_packet_cps, PACKET_HEADER_STRUCT


# The last four bytes of the MAC address is used as an ID field.
CLIENT_ID = get_mac().to_bytes(6, "little", signed=False)[-4:]


def write_packet(writer, packet_type, packet_id, timestamp, info, fields):
    encoded_packet = encode_packet(packet_type, packet_id, timestamp, info, fields)
    writer.write(encoded_packet)


async def read_packet(reader):
    header_buf = await reader.readexactly(PACKET_HEADER_STRUCT.size)
    size_remaining, decode_packet_body = decode_packet_cps(header_buf)
    body_buf = await reader.readexactly(size_remaining)
    return decode_packet_body(body_buf)


class Connection:

    def __init__(self, reader, writer, logger, *, loop=None):
        self._reader = reader
        self._writer = writer
        self.logger = logger
        self._loop = loop or asyncio.get_event_loop()
        # Packet reading.
        self._reader = None
        # Packet writing.
        self._id_gen = 0
        self._writer = None
        # Multiplexing.
        self._packet_reader = None

    def _gen_id(self):
        self._id_gen += 1
        return self._id_gen

    # Packet reading.

    async def _read_packet(self):
        try:
            packet = await read_packet(self._reader)
            self.logger.debug("Received packet %s %s", packet.type, packet.fields)
            return packet
        finally:
            self._packet_reader = None

    async def _wait_for_packet(self):
        if self._packet_reader is None:
            self._packet_reader = self._loop.create_task(self._read_packet())
        return (await asyncio.shield(self._packet_reader, loop=self._loop))

    # Connection lifecycle.

    def close(self):
        self._writer.write_eof()
        self._writer.close()
        self.logger.info("Closed")

    async def wait_closed(self):
        # Keep reading packets until we get an EOF, meaning that the connection was closed.
        while True:
            try:
                await self._wait_for_packet()
            except EOFError:
                return

    # Receiving fields.

    async def recv_field(self, packet_type, field_name, *, field_id=None):
        while True:
            packet = await self._wait_for_packet()
            if packet.type == packet_type:
                for field in packet.fields:
                    if field.name == field_name and (field_id is None or field.id == field_id):
                        return field.params

    # Sending packets.

    def send(self, packet_type, fields):
        # Encode the fields.
        fields = [
            Field(
                name=field_name,
                id=self._gen_id(),
                params=params,
            )
            for field_name, params
            in fields.items()
        ]
        # Sent the packet.
        write_packet(self._writer, packet_type, self._gen_id(), datetime.now(tz=timezone.utc), CLIENT_ID, fields)
        self.logger.debug("Sent packet %s %s", packet_type, fields)
