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
    Use :func:`start_server` or :func:`run_app` to create a :doc:`server`.

.. autoclass:: Connection
    :members:

.. autoclass:: Response
    :members:

.. autoclass:: Field
    :members:
"""

import asyncio
from datetime import datetime, timezone
from itertools import cycle
from uuid import getnode as get_mac
import warnings
from ncplib.errors import ConnectionError, ConnectionClosed
from ncplib.packets import encode_packet, decode_packet_cps, PACKET_HEADER_SIZE


__all__ = (
    "Connection",
    "Response",
    "Field",
)


# The last four bytes of the MAC address is used as an ID field.
CLIENT_ID = get_mac().to_bytes(6, "little")[-4:]


# ID generation.
_gen_id = cycle(range(2 ** 32)).__next__


_send_return_doc = """:return: A :class:`Response` providing access to any :class:`Field` instances received in reply to
            the sent packet.
        :rtype: Response
        :raises ValueError: if any of the packet, field or parameter names were not a valid :term:`identifier`, or any
            of the parameter values were invalid.
        :raises TypeError: if any of the parameter values were not one of the supported
            :doc:`value types <values>`.
        """

_recv_return_doc = """
        :raises ncplib.NCPError: if a field could not be retrieved from the connection.
        :return: The next :class:`Field` received.
        :rtype: Field

        """


class Field(dict):

    """
    A :term:`NCP field` received by a :class:`Connection`.

    Access :term:`NCP parameter` values using item access:

    .. code:: python

        print(field["PDAT"])

    .. attribute:: connection

        The :class:`Connection` that created this field.

    .. attribute:: packet_type

        The type of :term:`NCP packet` that contained this field. This will be a valid :term:`identifier`.

    .. attribute:: packet_timestamp

        A timezone-aware :class:`datetime.datetime` describing when the containing packet was sent.

    .. attribute:: name

        The name of the :term:`NCP field`. This will be a valid :term:`identifier`.

    .. attribute:: id

        The unique :class:`int` ID of this field.
    """

    __slots__ = ("connection", "packet_type", "packet_timestamp", "name", "id",)

    def __init__(self, connection, packet_type, packet_timestamp, name, id, params):
        super().__init__(params)
        self.connection = connection
        self.packet_type = packet_type
        self.packet_timestamp = packet_timestamp
        self.name = name
        self.id = id

    def __repr__(self):  # pragma: no cover
        return "<Field {packet_type!r} {field_name!r} {params!r}>".format(
            packet_type=self.packet_type,
            field_name=self.name,
            params=dict(self.items()),
        )

    def send(self, **params):
        """
        Sends a :term:`NCP packet` containing a single field in reply to this field.

        :param \\**params: Keyword arguments, one per :term:`NCP parameter`. Each parameter name should be a valid
            :term:`identifier`, and each parameter value should be one of the supported
            :doc:`value types <values>`.
        """
        return self.connection._send_packet(self.packet_type, [(self.name, self.id, params.items())])
    send.__doc__ += _send_return_doc


class AsyncIteratorMixin:

    __slots__ = ()

    def __aiter__(self):
        return self

    @asyncio.coroutine
    def __anext__(self):
        try:
            return (yield from self.recv())
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

    def __init__(self, connection, packet_type, expected_fields):
        self._connection = connection
        self._packet_type = packet_type
        self._expected_fields = expected_fields

    @asyncio.coroutine
    def recv(self):
        """
        Waits for the next :class:`Field` received in reply to the sent :term:`NCP packet`.

        This method is a *coroutine*.

        """
        while True:
            field = yield from self._connection.recv()
            if field.packet_type == self._packet_type and (field.name, field.id) in self._expected_fields:
                return field
    recv.__doc__ += _recv_return_doc

    @asyncio.coroutine
    def recv_field(self, field_name):
        """
        Waits for the next matching :class:`Field` received in reply to the sent :term:`NCP packet`.

        This method is a *coroutine*.

        .. hint::

            Prefer :meth:`recv` unless the sent packet contained multiple fields.

        :param str field_name: The field name, must be a valid :term:`identifier`.
        """
        while True:
            field = yield from self.recv()
            if field.name == field_name:
                return field
    recv_field.__doc__ += _recv_return_doc


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

    def __init__(self, reader, writer, predicate, *, loop, logger, remote_hostname, auto_link, send_errors):
        self._loop = loop
        # Logging.
        self.logger = logger
        self.logger.info("Connected to %s over NCP", remote_hostname)
        # Packet reading.
        self._reader = reader
        self._predicate = predicate
        self._field_buffer = []
        # Packet writing.
        self._writer = writer
        # Config.
        self.remote_hostname = remote_hostname
        self._auto_link = auto_link
        self._auto_link_task = None
        self._send_errors = send_errors

    @property
    def transport(self):
        """
        The :class:`asyncio.WriteTransport` used by this connection.
        """
        return self._writer.transport

    # Background tasks.

    @asyncio.coroutine
    def _run_auto_link(self):
        while not self.is_closing():
            self.send_packet("LINK")
            yield from asyncio.sleep(3, loop=self._loop)

    def _start_tasks(self):
        if self._auto_link:
            self._auto_link_task = self._loop.create_task(self._run_auto_link())

    # Receiving fields.

    @asyncio.coroutine
    def recv(self):
        """
        Waits for the next :class:`Field` received by the connection.

        This method is a *coroutine*.

        """
        while True:
            # Return buffered fields.
            if self._field_buffer:
                field = self._field_buffer.pop()
                self.logger.debug(
                    "Received field %s %s from %s over NCP",
                    field.packet_type, field.name, self.remote_hostname
                )
                if self._predicate(field):
                    return field
            # Read and decode the packet.
            try:
                header_buf = yield from self._reader.readexactly(PACKET_HEADER_SIZE)
                size_remaining, decode_packet_body = decode_packet_cps(header_buf)
                body_buf = yield from self._reader.readexactly(size_remaining)
            except asyncio.IncompleteReadError:
                raise ConnectionClosed("Connection closed")
            except OSError as ex:  # pragma: no cover
                raise ConnectionError(ex)
            packet_type, packet_id, packet_timestamp, packet_info, fields = decode_packet_body(body_buf)
            # Store the fields in the field buffer.
            self.logger.debug("Received packet %s from %s over NCP", packet_type, self.remote_hostname)
            self._field_buffer = [
                Field(self, packet_type, packet_timestamp, field_name, field_id, params)
                for field_name, field_id, params in fields
            ]
            self._field_buffer.reverse()
    recv.__doc__ += _recv_return_doc

    @asyncio.coroutine
    def recv_field(self, packet_type, field_name):
        """
        Waits for the next matching :class:`Field` received by the connection.

        This method is a *coroutine*.

        :param str packet_type: The packet type, must be a valid :term:`identifier`.
        :param str field_name: The field name, must be a valid :term:`identifier`.
        """
        while True:
            field = yield from self.recv()
            if field.packet_type == packet_type and field.name == field_name:
                return field
    recv_field.__doc__ += _recv_return_doc

    # Packet writing.

    def _send_packet(self, packet_type, fields):
        encoded_packet = encode_packet(packet_type, _gen_id(), datetime.now(tz=timezone.utc), CLIENT_ID, fields)
        self._writer.write(encoded_packet)
        self.logger.debug("Sent packet %s to %s over NCP", packet_type, self.remote_hostname)
        expected_fields = set()
        for field_name, field_id, params in fields:
            self.logger.debug("Sent field %s %s to %s over NCP", packet_type, field_name, self.remote_hostname)
            expected_fields.add((field_name, field_id))
        # Create an iterator of response fields.
        return Response(self, packet_type, expected_fields)

    # Sending fields.

    def send_packet(self, packet_type, **fields):
        """
        Sends a :term:`NCP packet` containing multiple :term:`NCP fields <NCP field>`.

        .. hint::

            Prefer :meth:`send` unless you need to send multiple fields in a single packet.

        :param str packet_type: The packet type, must be a valid :term:`identifier`.
        :param \\**fields: Keyword arguments, one per field. Each field name should be a valid :term:`identifier`, and
            the field value should be a :class:`dict` of parameter names mapped to parameter values. Each parameter name
            should be a valid :term:`identifier`, and each parameter value should be one of the supported
            :doc:`value types <values>`.
        """
        return self._send_packet(packet_type, [
            (field_name, _gen_id(), field_params.items())
            for field_name, field_params
            in fields.items()
        ])
    send_packet.__doc__ += _send_return_doc

    def send(self, packet_type, field_name, **params):
        """
        Sends a :term:`NCP packet` containing a single :term:`NCP field`.

        :param str packet_type: The packet type, must be a valid :term:`identifier`.
        :param str field_name: The field name, must be a valid :term:`identifier`.
        :param \\**params: Keyword arguments, one per :term:`NCP parameter`. Each parameter name should be a valid
            :term:`identifier`, and each parameter value should be one of the supported
            :doc:`value types <values>`.
        """
        return self._send_packet(packet_type, [(field_name, _gen_id(), params.items())])
    send.__doc__ += _send_return_doc

    # Connection lifecycle.

    def is_closing(self):
        """
        Returns True if the connection is closing.

        A closing connection should not be written to.
        """
        # HACK: The is_closing() API was only added in Python 3.5.1. This works in Python 3.4 as well.
        return self.transport._closing

    def close(self):
        """
        Closes the connection.

        .. hint::

            If you use the connection as an *async context manager*, there's no need to call :meth:`Connection.close`
            manually.
        """
        # Stop handlers.
        if self._auto_link and self._auto_link_task is not None:
            self._auto_link_task.cancel()
        # Close the connection.
        self._writer.close()
        self.logger.info("Disconnected from %s over NCP", self.remote_hostname)

    @asyncio.coroutine
    def wait_closed(self):
        warnings.warn("Connection.wait_closed() is a no-op, and will be removed in v3.0", DeprecationWarning)

    @asyncio.coroutine
    def __aenter__(self):
        return self

    @asyncio.coroutine
    def __aexit__(self, exc_type, exc, tb):
        self.close()
