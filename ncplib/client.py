import asyncio, logging
from datetime import datetime, timezone
from uuid import getnode as get_mac
from contextlib import contextmanager

from ncplib.errors import ClientError
from ncplib.decoder import decode_packet_size, decode_packet
from ncplib.encoder import encode_packet
from ncplib.constants import PACKET_HEADER_SIZE, PACKET_FOOTER_SIZE


logger = logging.getLogger(__name__)


_PACKET_INFO = get_mac().to_bytes(6, "little", signed=False)[-4:]  # The last four bytes of the MAC address is used as an ID field.


class Client:

    __slots__ = ("_host", "_port", "_loop", "_packet_id_gen", "_buf", "_buf_pos", "_stream_reader", "_stream_writer",)

    def __init__(self, host, port, *, loop=None):
        self._host = host
        self._port = port
        self._loop = loop or asyncio.get_event_loop()
        self._packet_id_gen = 0
        self._buf = bytearray(1024)
        self._buf_pos = 0
        self._stream_reader = None
        self._stream_writer = None

    def close(self):
        if self._stream_reader is not None:
            self._stream_reader = None
            self._stream_writer.close()
            self._stream_writer = None

    @asyncio.coroutine
    def _send_packet(self, packet_type, fields):
        # Encode the packet.
        self._packet_id_gen += 1
        packet_data = encode_packet(packet_type, self._packet_id_gen, datetime.now(tz=timezone.utc), _PACKET_INFO, fields)
        # Send the packet.
        self._stream_writer.write(packet_data)
        yield from self._stream_writer.drain()
        logger.debug("Client sent %s packet to %s:%s", packet_type, self._host, self._port)

    @asyncio.coroutine
    def _read_bytes(self, size):
        buf = self._buf
        # Grow the buffer if required.
        if len(buf) < self._buf_pos + size:
            buf = bytearray(len(buf) * 2)
            buf[:len(self._buf)] = self._buf
            self._buf = buf
        # Read into the buffer.
        while size > 0:
            data = yield from self._stream_reader.read(size)
            buf[self._buf_pos:len(data)] = data
            self._buf_pos += len(data)
            size -= len(data)

    @asyncio.coroutine
    def _recv_packet(self):
        self._buf_pos = 0
        yield from self._read_bytes(PACKET_HEADER_SIZE + PACKET_FOOTER_SIZE)
        # Peek at the packet size, so we know how much more to read.
        with memoryview(self._buf) as data:
            packet_size = decode_packet_size(data)
            logger.debug("Client receiving packet from %s:%s (%s bytes)", self._host, self._port, packet_size)
        # Read the remaining bytes.
        yield from self._read_bytes(packet_size - PACKET_HEADER_SIZE - PACKET_FOOTER_SIZE)
        # Decode the packet.
        with memoryview(self._buf) as data:
            packet = decode_packet(data[:self._buf_pos])
            logger.debug("Client received %s packet from %s:%s %s", packet.type, self._host, self._port, packet)
            return packet

    @asyncio.coroutine
    def _ensure_connection(self):
        if self._stream_reader is None:
            # Connect to the NCP server.
            self._stream_reader, self._stream_writer = yield from asyncio.open_connection(self._host, self._port, loop=self._loop)
            logger.debug("Client connected to %s:%s", self._host, self._port)
            # Read the initial LINK HELO packet.
            helo_packet = yield from self._recv_packet()
            if helo_packet.type != b"LINK" and b"HELO" not in helo_packet.fields:  # pragma: no cover
                raise ClientError("Did not receive LINK HELO packet from %s:%s", self._host, self._port)

    @contextmanager
    def _auto_disconnect(self):
        try:
            yield
        except:  # pragma: no cover
            # Kill the broken connection.
            self._stream_reader = None
            self._stream_writer = None
            raise

    # Public API.

    @asyncio.coroutine
    def connect(self):
        with self._auto_disconnect():
            yield from self._ensure_connection()

    @asyncio.coroutine
    def execute(self, packet_type, fields):
        with self._auto_disconnect():
            yield from self._ensure_connection()
            yield from self._send_packet(packet_type, fields)
            return (yield from self._recv_packet())
