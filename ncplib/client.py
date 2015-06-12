import asyncio
from datetime import datetime, timezone
from uuid import getnode as get_mac

from ncplib.concurrent import sync, SyncWrapper
from ncplib.streams import write_packet, read_packet


PACKET_INFO = get_mac().to_bytes(6, "little", signed=False)[-4:]  # The last four bytes of the MAC address is used as an ID field.


class Client:

    __slots__ = ("_host", "_port", "_loop", "_timeout", "_packet_id_gen", "_reader", "_writer",)

    def __init__(self, host, port, *, loop=None, timeout=None):
        self._host = host
        self._port = port
        self._loop = loop or asyncio.get_event_loop()
        self._timeout = None
        self._packet_id_gen = 0
        self._reader = None
        self._writer = None

    # Connection lifecycle.

    def _wait_for(self, task):
        return asyncio.wait_for(task, self._timeout, loop=self._loop)

    @asyncio.coroutine
    def _connect(self):
        # Connect to the node.
        self._reader, self._writer = yield from self._wait_for(asyncio.open_connection(self._host, self._port, loop=self._loop))
        # Read the initial LINK HELO packet.
        helo_packet = yield from self._read_packet()
        assert helo_packet.type == b"LINK" and b"HELO" in helo_packet.fields

    def close(self):
        self._writer.close()

    # Packet implementation.

    @asyncio.coroutine
    def _read_packet(self):
        return (yield from read_packet(self._reader))

    @asyncio.coroutine
    def _write_packet(self, packet_type, fields):
        self._packet_id_gen += 1
        yield from self._wait_for(write_packet(self._writer, packet_type, self._packet_id_gen, datetime.now(tz=timezone.utc), PACKET_INFO, fields))

    # Public API.

    @asyncio.coroutine
    def communicate(self, packet_type, fields):
        yield from self._write_packet(packet_type, fields)
        return (yield from self._wait_for(self._read_packet()))


@asyncio.coroutine
def connect(host, port, *, loop=None, timeout=None):
    client = Client(host, port, loop=loop, timeout=timeout)
    yield from client._connect()
    return client


def connect_sync(host, port, *, loop=None, timeout=None):
    client = sync(loop=loop)(connect)(host, port, loop=loop, timeout=timeout)
    return SyncWrapper(client)
