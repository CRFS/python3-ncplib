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
        self.packet = packet
        self.field = field

    def __getitem__(self, name):
        return self.field.params[name]

    def __iter__(self):
        return iter(self.field.params)

    def __len__(self):
        return len(self.field)

    def send(self, **params):
        return self.connection._send_packet(self.packet.type, [Field(self.field.name, self.field.id, params)])


class AsyncMessageIterator:

    def __init__(self, connection, predicate, message_list):
        self.connection = connection
        self._predicate = predicate
        self._message_list = message_list

    async def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return await self.recv()
        except EOFError:
            raise StopAsyncIteration

    def filter(self, predicate):
        return self.__class__(
            self.connection,
            lambda message: self._predicate(message) and predicate(message),
            self._message_list,
        )

    async def recv(self):
        while True:
            while not self._message_list:
                self._message_list = await self.connection._recv_packet()
            while self._message_list:
                message = self._message_list.pop(0)
                if self._predicate(message):
                    return message

    def recv_field(self, field_name):
        return self.filter(lambda message: message.field.name == field_name).recv()


class ConnectionLoggerAdapter(logging.LoggerAdapter):

    def process(self, msg, kwargs):
        msg, kwargs = super().process(msg, kwargs)
        return "ncp://{host}:{port} - {msg}".format(
            msg=msg,
            **self.extra
        ), kwargs


def base_message_predicate(message):
    return True


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

    # Receiving fields.

    def __aiter__(self):
        return AsyncMessageIterator(self, base_message_predicate, [])

    def recv(self):
        return self.__aiter__().recv()

    def recv_field(self, packet_type, field_name):
        return self.__aiter__().filter(lambda message: (
            message.packet.type == packet_type and
            message.field.name == field_name
        )).recv()

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
        return self.__aiter__().filter(lambda message: (
            message.packet.type == packet_type and
            (message.field.name, message.field.id) in expected_fields
        ))

    # Sending fields.

    def send_many(self, packet_type, fields):
        return self._send_packet(packet_type, [
            Field(field_name, self._gen_id(), field_params)
            for field_name, field_params
            in fields.items()
        ])

    def send(self, packet_type, field_name, **params):
        # Handle deprecated send signature.
        if isinstance(field_name, Mapping):
            warnings.warn(DeprecationWarning("Use send_many() to send multiple fields in one packet."))
            return self.send_many(packet_type, field_name)
        # Handle new send signature.
        return self._send_packet(packet_type, [Field(field_name, self._gen_id(), params)])

    # Connection lifecycle.

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
