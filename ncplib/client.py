import asyncio, logging
from datetime import datetime, timezone
from uuid import getnode as get_mac
from contextlib import contextmanager

from ncplib.streams import write_packet, read_packet


PACKET_INFO = get_mac().to_bytes(6, "little", signed=False)[-4:]  # The last four bytes of the MAC address is used as an ID field.


class Client:

    __slots__ = ("_host", "_port", "_loop", "_packet_id_gen", "_reader", "_writer",)

    def __init__(self, host, port, *, loop=None):
        self._host = host
        self._port = port
        self._loop = loop or asyncio.get_event_loop()
        self._packet_id_gen = 0
        self._reader = None
        self._writer = None

    def close(self):
        if self._reader is not None:
            self._reader = None
            self._writer.close()
            self._writer = None

    @asyncio.coroutine
    def _read_packet(self):
        return (yield from read_packet(self._reader))

    @asyncio.coroutine
    def _write_packet(self, packet_type, fields):
        self._packet_id_gen += 1
        yield from write_packet(self._writer, packet_type, self._packet_id_gen, datetime.now(tz=timezone.utc), PACKET_INFO, fields)

    @asyncio.coroutine
    def _ensure_connection(self):
        if self._reader is None or self._reader.at_eof() or self._reader.exception() is not None:
            # Connect to the NCP server.
            self._reader, self._writer = yield from asyncio.open_connection(self._host, self._port, loop=self._loop)
            # Read the initial LINK HELO packet.
            helo_packet = yield from self._read_packet()
            assert helo_packet.type == b"LINK" and b"HELO" in helo_packet.fields

    @contextmanager
    def _auto_disconnect(self):
        try:
            yield
        except:
            self._reader = None
            self._writer = None
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
            yield from self._write_packet(packet_type, fields)
            return (yield from self._read_packet())
