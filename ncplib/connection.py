import asyncio
import logging
import warnings
from collections.abc import Mapping
from datetime import datetime, timezone
from uuid import getnode as get_mac
from ncplib.packets import Field, encode_packet, decode_packet_cps, PACKET_HEADER_STRUCT


# The last four bytes of the MAC address is used as an ID field.
CLIENT_ID = get_mac().to_bytes(6, "little", signed=False)[-4:]


class Message(Mapping):

    def __init__(self, connection, packet, field):
        self.connection = connection
        self._packet = packet
        self._field = field

    @property
    def packet_type(self):
        return self._packet.type

    @property
    def packet_timestamp(self):
        return self._packet.timestamp

    @property
    def field_name(self):
        return self._field.name

    @property
    def field_id(self):
        return self._field.id

    def __getitem__(self, name):
        return self._field.params[name]

    def __iter__(self):
        return iter(self._field.params)

    def __len__(self):
        return len(self._field.params)

    def send(self, **params):
        return self.connection._send_packet(self.packet_type, [Field(self.field_name, self.field_id, params)])


class Response:

    def __init__(self, connection, predicate, message_list):
        self.connection = connection
        self._predicate = predicate
        self._message_list = message_list

    async def __aiter__(self):  # pragma: no cover
        return self

    async def __anext__(self):
        try:
            return await self.recv()
        except EOFError:
            raise StopAsyncIteration

    async def recv(self):
        while True:
            while not self._message_list:
                self._message_list = await self.connection._recv_packet()
            while self._message_list:
                message = self._message_list.pop(0)
                if self._predicate(message):
                    return message

    async def recv_field(self, field_name):
        async for message in self:
            if message.field_name == field_name:
                return message


class ConnectionLoggerAdapter(logging.LoggerAdapter):

    def process(self, msg, kwargs):
        msg, kwargs = super().process(msg, kwargs)
        return "ncp://{host}:{port} - {msg}".format(
            msg=msg,
            **self.extra
        ), kwargs


class Connection:

    def __init__(self, host, port, reader, writer, logger, *, loop=None):
        # Logging.
        self._host = host
        self._port = port
        self.logger = ConnectionLoggerAdapter(logger, {
            "host": host,
            "port": port,
        })
        # Packet reading.
        self._reader = reader
        # Packet writing.
        self._writer = writer
        self._id_gen = 0
        # Asyncio.
        self._loop = loop or asyncio.get_event_loop()
        # Multiplexing.
        self._packet_receiver = None

    def _gen_id(self):
        self._id_gen += 1
        return self._id_gen

    # Packet reading.

    def _message_predicate(self, message):
        return True

    async def _recv_packet_primary(self):
        try:
            # Decode the packet.
            header_buf = await self._reader.readexactly(PACKET_HEADER_STRUCT.size)
            size_remaining, decode_packet_body = decode_packet_cps(header_buf)
            body_buf = await self._reader.readexactly(size_remaining)
            packet = decode_packet_body(body_buf)
            self.logger.debug("Received packet %s %s", packet.type, packet.fields)
            # All done!
            return list(filter(self._message_predicate, (
                Message(self, packet, field)
                for field
                in packet.fields
            )))
        finally:
            self._packet_receiver = None

    async def _recv_packet(self):
        if self._packet_receiver is None:
            self._packet_receiver = self._loop.create_task(self._recv_packet_primary())
        return (await asyncio.shield(self._packet_receiver, loop=self._loop))

    # Receiving messages.

    async def __aiter__(self):
        return Response(self, lambda message: True, [])

    async def recv(self):
        return await (await self.__aiter__()).recv()

    async def recv_field(self, packet_type, field_name):
        async for message in self:
            if message.packet_type == packet_type and message.field_name == field_name:
                return message

    # Packet writing.

    def _send_packet(self, packet_type, fields):
        encoded_packet = encode_packet(packet_type, self._gen_id(), datetime.now(tz=timezone.utc), CLIENT_ID, fields)
        self._writer.write(encoded_packet)
        self.logger.debug("Sent packet %s %s", packet_type, fields)
        # Create an iterator of response fields.
        expected_fields = frozenset(
            (field.name, field.id)
            for field
            in fields
        )
        return Response(self, lambda message: (
            message.packet_type == packet_type and
            (message.field_name, message.field_id) in expected_fields
        ), [])

    # Sending fields.

    def send_packet(self, packet_type, **fields):
        return self._send_packet(packet_type, [
            Field(field_name, self._gen_id(), field_params)
            for field_name, field_params
            in fields.items()
        ])

    def send(self, packet_type, field_name, **params):
        # Handle deprecated send signature.
        if isinstance(field_name, Mapping):
            warnings.warn(DeprecationWarning("Use send_packet() to send multiple fields in one packet."))
            return self.send_packet(packet_type, **field_name)
        # Handle new send signature.
        return self._send_packet(packet_type, [Field(field_name, self._gen_id(), params)])

    def execute(self, packet_type, field_name, params=None):
        warnings.warn(DeprecationWarning("Use send(packet_type, field_name, **params).recv() instead of execute()."))
        return self.send(packet_type, field_name, **(params or {})).recv()

    # Connection lifecycle.

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.close()
        await self.wait_closed()

    def close(self):
        self._writer.write_eof()
        self._writer.close()
        self.logger.info("Closed")

    async def wait_closed(self):
        # Keep reading packets until we get an EOF, meaning that the connection was closed.
        while True:
            try:
                await self._recv_packet()
            except EOFError:
                return
