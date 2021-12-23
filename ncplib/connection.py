"""
NCP connection
==============

.. currentmodule:: ncplib

:term:`NCP` connections are used by the :doc:`client` and :doc:`server` to represent each side of a connection.

Overview
--------

Getting started
^^^^^^^^^^^^^^^

-   :doc:`NCP client documentation <client>`.
-   :doc:`NCP server documentation <client>`.


Spawning tasks
^^^^^^^^^^^^^^

Spawn a concurrent task to handle long-running commands:

.. code::

    import asyncio

    loop = asyncio.get_event_loop()

    async def handle_dspc_time(field):
        field.send(ACKN=1)
        await asyncio.sleep(10)  # Simulate a blocking task.
        field.send(TSDC=0, TIMM=1)

    for field in connection:
        if field.packet_type == "DSPC" and field.name == "TIME":
            # Spawn a concurrent task to avoid blocking the accept loop.
            loop.create_task(handle_dspc_time(field))
        # Handle other field types here.


API reference
-------------

.. important::

    Do not instantiate these classes directly. Use :func:`connect` to create a :doc:`client` connection.
    Use :func:`start_server` to create a :doc:`server`.

.. autoclass:: Connection
    :members:

.. autoclass:: Response
    :members:

.. autoclass:: Field
    :members:
"""
from __future__ import annotations
import asyncio
from async_timeout import timeout
from datetime import datetime, timezone
from itertools import cycle
import logging
from time import time
from types import TracebackType
from typing import AsyncIterator, Awaitable, Callable, Dict, List, Mapping, Optional, Set, Tuple, Type, TypeVar
from uuid import getnode as get_mac
import warnings
from ncplib.errors import NetworkError, NetworkTimeoutError, ConnectionClosed, DecodeError, DecodeWarning
from ncplib.packets import Packet, Param, Params, Fields, encode_packet, decode_packet_cps, PACKET_HEADER_SIZE


T = TypeVar("T")


# The last four bytes of the MAC address is used as an ID field.
CLIENT_ID = get_mac().to_bytes(6, "little")[-4:]

# The footer and other metadata for the LINK heartbeat packet trailer.
LINK_TRAILER = b"".join((b'\x00\x00\x00\x00', CLIENT_ID, b'\x00\x00\x00\x00\xaa\xbb\xcc\xdd'))

# ID generation.
_gen_id = cycle(range(2 ** 32)).__next__


DEFAULT_TIMEOUT: int = 60


async def _wait_for(coro: Awaitable[T], ms: int) -> T:
    try:
        async with timeout(ms):
            return await coro
    except asyncio.CancelledError:  # pragma: no cover
        raise  # Propagate cancels, not needed in Python3.8+.
    except asyncio.TimeoutError as ex:  # pragma: no cover
        raise NetworkTimeoutError(ex) from ex
    except OSError as ex:  # pragma: no cover
        raise NetworkError(ex) from ex


def _decode_remote_timeout(field: Field) -> int:
    remote_timeout = field.get("LINK", 0)
    if isinstance(remote_timeout, (int, float)) and remote_timeout >= 0:
        return int(remote_timeout)
    warnings.warn(DecodeWarning(f"Invalid {field.packet_type} {field.name} LINK param: {remote_timeout!r}"))
    return 0


def _handle_tunnel_args(port: Optional[int], ssl: bool, authenticate: bool) -> Tuple[int, bool]:
    default_port: int
    if ssl:
        default_port = 443
    elif authenticate:
        default_port = 80
    else:
        default_port = 9999
    return (default_port if port is None else port, ssl or authenticate)


class Field(Dict[str, Param]):

    """
    A :term:`NCP field` received by a :class:`Connection`.

    Access :term:`NCP parameter` values using item access:

    .. code:: python

        print(field["PDAT"])

    .. attribute:: connection

        The :class:`Connection` that created this field.

    .. attribute:: packet_type

        The type of :term:`NCP packet` that contained this field. This will be a valid :term:`identifier`.

    .. attribute:: packet_id

        The ID of the of :term:`NCP packet` that contained this field.

    .. attribute:: packet_timestamp

        A timezone-aware :class:`datetime.datetime` describing when the containing packet was sent.

    .. attribute:: name

        The name of the :term:`NCP field`. This will be a valid :term:`identifier`.

    .. attribute:: id

        The unique :class:`int` ID of this field.
    """

    __slots__ = ("connection", "packet_type", "packet_id", "packet_timestamp", "name", "id",)

    connection: Connection
    packet_type: str
    packet_id: int
    packet_timestamp: datetime
    name: str
    id: int

    def __init__(
        self, connection: Connection,
        packet_type: str, packet_id: int, packet_timestamp: datetime,
        name: str, id: int, params: Params,
    ) -> None:
        super().__init__(params)
        self.connection = connection
        self.packet_type = packet_type
        self.packet_id = packet_id
        self.packet_timestamp = packet_timestamp
        self.name = name
        self.id = id

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Field {self.packet_type!r} {self.name!r} {dict(self.items())!r}>"

    def send(self, **params: Param) -> Response:
        """
        Sends a :term:`NCP packet` containing a single field in reply to this field.

        :param \\**params: Keyword arguments, one per :term:`NCP parameter`. Each parameter name should be a valid
            :term:`identifier`, and each parameter value should be one of the supported
            :doc:`value types <values>`.
        :return: A :class:`Response` providing access to any :class:`Field` instances received in reply to
            the sent packet.
        :rtype: Response
        :raises ValueError: if any of the packet, field or parameter names were not a valid :term:`identifier`, or any
            of the parameter values were invalid.
        :raises TypeError: if any of the parameter values were not one of the supported
            :doc:`value types <values>`.
        """
        return self.connection._send_packet(self.packet_type, ((self.name, self.id, params.items()),))


class AsyncIteratorMixin:

    __slots__ = ()

    def __aiter__(self) -> AsyncIterator[Field]:
        return self

    async def __anext__(self) -> Field:
        try:
            return await self.recv()  # type: ignore
        except ConnectionClosed:
            raise StopAsyncIteration


class Response(AsyncIteratorMixin):

    """
    A response to a :term:`NCP packet`, returned by :meth:`Connection.send`, :meth:`Connection.send_packet` and
    :meth:`Field.send`.

    Provides access to any :class:`Field` received in reply to the sent packet.

    Responses can be used as *async iterators* to loop over each incoming :class:`Field`:

    .. code:: python

        async for field in response:
            pass

    .. important::
        The *async for loop* will only terminate when the underlying connection closes.
    """

    __slots__ = ("_connection", "_packet_type", "_expected_fields")

    _connection: Connection
    _packet_type: str
    _expected_fields: Set[Tuple[str, int]]

    def __init__(
        self, connection: Connection,
        packet_type: str,
        expected_fields: Set[Tuple[str, int]],
    ) -> None:
        self._connection = connection
        self._packet_type = packet_type
        self._expected_fields = expected_fields

    async def recv(self) -> Field:
        """
        Waits for the next :class:`Field` received in reply to the sent :term:`NCP packet`.

        :raises ncplib.NCPError: if a field could not be retrieved from the connection.
        :return: The next :class:`Field` received.
        :rtype: Field
        """
        while True:
            field = await self._connection.recv()
            if (
                field.packet_type == self._packet_type and
                (field.name, field.id) in self._expected_fields
            ):
                return field

    async def recv_field(self, field_name: str) -> Field:
        """
        Waits for the next matching :class:`Field` received in reply to the sent :term:`NCP packet`.

        .. hint::

            Prefer :meth:`recv` unless the sent packet contained multiple fields.

        :param str field_name: The field name, must be a valid :term:`identifier`.
        :raises ncplib.NCPError: if a field could not be retrieved from the connection.
        :return: The next :class:`Field` received.
        :rtype: Field
        """
        while True:
            field = await self.recv()
            if field.name == field_name:
                return field


class Connection(AsyncIteratorMixin):

    """
    A connection between a :doc:`client` and a :doc:`server`.

    Connections can be used as *async iterators* to loop over each incoming :class:`Field`:

    .. code:: python

        async for field in connection:
            pass

    .. important::
        The *async for loop* will only terminate when the underlying connection closes.

    Connections can also be used as *async context managers* to automatically close the connection:

    .. code:: python

        async with connection:
            pass

        # Connection is automatically closed.

    .. attribute:: logger

        The :class:`logging.Logger` used by this connection. Log messages will be prefixed with the host and port of
        the connection.

    .. attribute:: remote_hostname

        The identifying hostname for the remote end of the connection.

    """

    _loop: asyncio.AbstractEventLoop
    logger: logging.Logger
    _reader: asyncio.StreamReader
    _predicate: Callable[[Field], bool]
    _field_buffer: List[Field]
    _timeout: int
    _writer: asyncio.StreamWriter
    _remote_timeout: int
    _link_send_interval: int
    _link_send_handle: Optional[asyncio.Handle]
    remote_hostname: str

    def __init__(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, predicate: Callable[[Field], bool], *,
        logger: logging.Logger,
        remote_hostname: str,
        timeout: int,
    ):
        self._loop = asyncio.get_running_loop()
        # Logging.
        self.logger = logger
        self.logger.info("Connected to %s over NCP", remote_hostname)
        # Packet reading.
        self._reader = reader
        self._predicate = predicate  # type: ignore
        self._field_buffer = []
        self._timeout = timeout
        # Packet writing.
        self._writer = writer
        self._remote_timeout = 0
        self._link_send_interval = 3
        self._link_send_handle = None
        # Config.
        self.remote_hostname = remote_hostname

    @property
    def transport(self) -> asyncio.BaseTransport:
        """
        The :class:`asyncio.WriteTransport` used by this connection.
        """
        return self._writer.transport

    # Background tasks.

    def _send_link(self) -> None:
        self._writer.write(b"".join((
            b'\xdd\xcc\xbb\xaaLINK\n\x00\x00\x00\x00\x00\x00\x00\x01\x00\x00\x00',
            int(time()).to_bytes(4, "little"),
            LINK_TRAILER,
        )))
        self.logger.debug("Sent keep-alive to %s over NCP", self.remote_hostname)
        self._send_link_soon()

    def _send_link_soon(self) -> None:
        self._link_send_handle = self._loop.call_later(self._link_send_interval, self._send_link)

    def _apply_remote_timeout(self, remote_timeout: int) -> None:
        if remote_timeout == 0:
            # The remote does not understand CCRE LINK. Use legacy behaviour.
            self._send_link()
        else:
            # The remote understands CCRE LINK. Configure the connection appropriately.
            self._timeout = remote_timeout
            self._remote_timeout = remote_timeout
            self._link_send_interval = int(remote_timeout * 0.66)
            # Send the first link packet in the future.
            self._send_link_soon()

    # Receiving fields.

    async def _recv_packet(self) -> Packet:
        # Read the header. If there's no more data in the pipe, it's a graceful close.
        try:
            header_buf = await self._reader.readexactly(PACKET_HEADER_SIZE)
        except asyncio.IncompleteReadError as ex:
            if len(ex.partial) == 0:
                raise ConnectionClosed("Connection closed") from ex
            raise DecodeError(ex) from ex  # pragma: no cover
        # Read the body. This has to be present, or it's an unexpected close.
        size_remaining, decode_packet_body = decode_packet_cps(header_buf)
        try:
            body_buf = await self._reader.readexactly(size_remaining)
        except asyncio.IncompleteReadError as ex:  # pragma: no cover
            raise DecodeError(ex) from ex
        return decode_packet_body(body_buf)

    async def recv(self) -> Field:
        """
        Waits for the next :class:`Field` received by the connection.

        :raises ncplib.NCPError: if a field could not be retrieved from the connection.
        :return: The next :class:`Field` received.
        :rtype: Field
        """
        while True:
            # Return buffered fields.
            if self._field_buffer:
                field = self._field_buffer.pop()
                self.logger.debug(
                    "Received field %s %s from %s over NCP",
                    field.packet_type, field.name, self.remote_hostname
                )
                if self._predicate(field):  # type: ignore
                    return field
            packet_type, packet_id, packet_timestamp, packet_info, fields = await _wait_for(
                self._recv_packet(),
                self._timeout,
            )
            # Store the fields in the field buffer.
            self.logger.debug("Received packet %s from %s over NCP", packet_type, self.remote_hostname)
            self._field_buffer = [
                Field(self, packet_type, packet_id, packet_timestamp, field_name, field_id, params)
                for field_name, field_id, params in fields
            ]
            self._field_buffer.reverse()

    async def recv_field(self, packet_type: str, field_name: str) -> Field:
        """
        Waits for the next matching :class:`Field` received by the connection.

        :param str packet_type: The packet type, must be a valid :term:`identifier`.
        :param str field_name: The field name, must be a valid :term:`identifier`.
        :raises ncplib.NCPError: if a field could not be retrieved from the connection.
        :return: The next :class:`Field` received.
        :rtype: Field
        """
        while True:
            field = await self.recv()
            if field.packet_type == packet_type and field.name == field_name:
                return field

    # Packet writing.

    def _send_packet(self, packet_type: str, fields: Fields) -> Response:
        encoded_packet = encode_packet(packet_type, 1, datetime.now(tz=timezone.utc), CLIENT_ID, fields)
        self._writer.write(encoded_packet)
        self.logger.debug("Sent packet %s to %s over NCP", packet_type, self.remote_hostname)
        expected_fields = set()
        for field_name, field_id, params in fields:
            self.logger.debug("Sent field %s %s to %s over NCP", packet_type, field_name, self.remote_hostname)
            expected_fields.add((field_name, field_id))
        # If the connection supports CCRE LINK, we can defer the LINK send.
        if self._remote_timeout > 0 and self._link_send_handle is not None:
            self._link_send_handle.cancel()
            self._send_link_soon()
        # Create an iterator of response fields.
        return Response(self, packet_type, expected_fields)

    # Sending fields.

    def send_packet(self, packet_type: str, **fields: Mapping[str, Param]) -> Response:
        """
        Sends a :term:`NCP packet` containing multiple :term:`NCP fields <NCP field>`.

        .. hint::

            Prefer :meth:`send` unless you need to send multiple fields in a single packet.

        :param str packet_type: The packet type, must be a valid :term:`identifier`.
        :param \\**fields: Keyword arguments, one per field. Each field name should be a valid :term:`identifier`, and
            the field value should be a :class:`dict` of parameter names mapped to parameter values. Each parameter name
            should be a valid :term:`identifier`, and each parameter value should be one of the supported
            :doc:`value types <values>`.
        :return: A :class:`Response` providing access to any :class:`Field` instances received in reply to
            the sent packet.
        :rtype: Response
        :raises ValueError: if any of the packet, field or parameter names were not a valid :term:`identifier`, or any
            of the parameter values were invalid.
        :raises TypeError: if any of the parameter values were not one of the supported
            :doc:`value types <values>`.
        """
        return self._send_packet(packet_type, [
            (field_name, _gen_id(), field_params.items())
            for field_name, field_params
            in fields.items()
        ])

    def send(self, packet_type: str, field_name: str, **params: Param) -> Response:
        """
        Sends a :term:`NCP packet` containing a single :term:`NCP field`.

        :param str packet_type: The packet type, must be a valid :term:`identifier`.
        :param str field_name: The field name, must be a valid :term:`identifier`.
        :param \\**params: Keyword arguments, one per :term:`NCP parameter`. Each parameter name should be a valid
            :term:`identifier`, and each parameter value should be one of the supported
            :doc:`value types <values>`.
        :return: A :class:`Response` providing access to any :class:`Field` instances received in reply to
            the sent packet.
        :rtype: Response
        :raises ValueError: if any of the packet, field or parameter names were not a valid :term:`identifier`, or any
            of the parameter values were invalid.
        :raises TypeError: if any of the parameter values were not one of the supported
            :doc:`value types <values>`.
        """
        return self._send_packet(packet_type, ((field_name, _gen_id(), params.items()),))

    # Connection lifecycle.

    def is_closing(self) -> bool:
        """
        Returns True if the connection is closing.

        A closing connection should not be written to.
        """
        return self.transport.is_closing()

    def close(self) -> None:
        """
        Closes the connection.

        .. hint::

            If you use the connection as an *async context manager*, there's no need to call :meth:`Connection.close`
            manually.
        """
        # Stop handlers.
        if self._link_send_handle is not None:
            self._link_send_handle.cancel()
            self._link_send_handle = None
        # Close the connection.
        self._writer.close()
        self.logger.info("Disconnected from %s over NCP", self.remote_hostname)

    async def wait_closed(self) -> None:
        """
        Waits for the connection to finish closing.

        .. hint::

            If you use the connection as an *async context manager*, there's no need to call
            :meth:`Connection.wait_closed` manually.
        """
        await _wait_for(self._writer.wait_closed(), self._timeout)

    async def __aenter__(self: T) -> T:
        return self

    async def __aexit__(self, exc_type: Optional[Type[T]], exc: Optional[T], tb: Optional[TracebackType]) -> None:
        self.close()
        await self.wait_closed()
