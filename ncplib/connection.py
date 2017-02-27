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
from collections import deque
from collections.abc import Mapping
from datetime import datetime, timezone
from uuid import getnode as get_mac
from ncplib.errors import DecodeError, CommandError
from ncplib.packets import FieldData, encode_packet, decode_packet_cps, PACKET_HEADER_STRUCT


__all__ = (
    "Connection",
    "Response",
    "Field",
)


# The last four bytes of the MAC address is used as an ID field.
CLIENT_ID = get_mac().to_bytes(6, "little", signed=False)[-4:]


_send_return_doc = """:return: A :class:`Response` providing access to any :class:`Field` instances received in reply to
            the sent packet.
        :rtype: Response
        :raises ValueError: if any of the packet, field or parameter names were not a valid :term:`identifier`, or any
            of the parameter values were invalid.
        :raises TypeError: if any of the parameter values were not one of the supported
            :doc:`value types <values>`.
        """

_recv_return_doc = """:return: The next :class:`Field` received.
        :rtype: Field
        :raises ncplib.CommandError: if the incoming field contains an ``ERRO`` parameter, and this is a :doc:`client`
            connection with ``auto_erro`` enabled.
        :raises ncplib.DecodeError: if the incoming field was part of an invalid :term:`NCP packet`.
        :raises asyncio.IncompleteReadError: if the connection closed unexpectedly.
        """


class Field(Mapping):

    """
    A :term:`NCP field` received by a :class:`Connection`.

    Access :term:`NCP parameter` values using item access:

    .. code:: python

        print(field["PDAT"])
    """

    def __init__(self, connection, packet, field):
        self._connection = connection
        self._packet = packet
        self._field = field

    @property
    def packet_type(self):
        """
        The type of :term:`NCP packet` that contained this field. This will be a valid :term:`identifier`.
        """
        return self._packet.type

    @property
    def packet_timestamp(self):
        """
        A timezone-aware :class:`datetime.datetime` describing when the containing packet was sent.
        """
        return self._packet.timestamp

    @property
    def name(self):
        """
        The name of the :term:`NCP field`. This will be a valid :term:`identifier`.
        """
        return self._field.name

    @property
    def id(self):
        """
        The unique :class:`int` ID of this field.
        """
        return self._field.id

    def __getitem__(self, name):
        return self._field.params[name]

    def __iter__(self):
        return iter(self._field.params)

    def __len__(self):
        return len(self._field.params)

    def __repr__(self):  # pragma: no cover
        return "<Field {packet_type!r} {field_name!r} {params!r}>".format(
            packet_type=self.packet_type,
            field_name=self.name,
            params=dict(self._field.params.items()),
        )

    def send(self, **params):
        """
        Sends a :term:`NCP packet` containing a single field in reply to this field.

        :param \\**params: Keyword arguments, one per :term:`NCP parameter`. Each parameter name should be a valid
            :term:`identifier`, and each parameter value should be one of the supported
            :doc:`value types <values>`.
        """
        return self._connection._send_packet(self.packet_type, [FieldData(self.name, self.id, params)])
    send.__doc__ += _send_return_doc


class AsyncHandlerMixin:

    def __init__(self, *, loop):
        self._loop = loop or asyncio.get_event_loop()
        self._handlers = set()

    def create_handler(self, coro):
        handler = self._loop.create_task(coro)
        self._handlers.add(handler)
        handler.add_done_callback(self._handlers.remove)
        return handler

    def close(self):
        for handler in self._handlers:
            handler.cancel()

    @asyncio.coroutine
    def wait_closed(self):
        if self._handlers:
            yield from asyncio.wait(self._handlers, loop=self._loop)


class AsyncIteratorMixin:

    def __aiter__(self):
        return self

    @asyncio.coroutine
    def __anext__(self):
        try:
            return (yield from self.recv())
        except EOFError:
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

    def __init__(self, connection, predicate):
        self._connection = connection
        self._predicate = predicate

    @asyncio.coroutine
    def recv(self):
        """
        Waits for the next :class:`Field` received in reply to the sent :term:`NCP packet`.

        This method is a *coroutine*.

        """
        while True:
            field = yield from self._connection.recv()
            if self._predicate(field):
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


class ClosableContextMixin:

    @asyncio.coroutine
    def __aenter__(self):
        return self

    @asyncio.coroutine
    def __aexit__(self, exc_type, exc, tb):
        self.close()
        yield from self.wait_closed()


class Connection(AsyncHandlerMixin, AsyncIteratorMixin, ClosableContextMixin):

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

    def __init__(self, reader, writer, *, loop, logger, remote_hostname, auto_link):
        super().__init__(loop=loop)
        # Logging.
        self.logger = logger
        self.logger.debug("Connected to %s over NCP", remote_hostname)
        # Packet reading.
        self._reader = reader
        self._field_buffer = deque()
        # Packet writing.
        self._writer = writer
        self._id_gen = 0
        # Config.
        self.remote_hostname = remote_hostname
        self._auto_link = auto_link

    @property
    def transport(self):
        """
        The :class:`asyncio.WriteTransport` used by this connection.
        """
        return self._writer.transport

    def _gen_id(self):
        self._id_gen += 1
        return self._id_gen

    # Handlers.

    @asyncio.coroutine
    def _connect(self):
        if self._auto_link:
            self.create_handler(self._handle_link())

    @asyncio.coroutine
    def _handle_link(self):
        while not self.transport._closing:
            self.send_packet("LINK")
            yield from asyncio.sleep(3, loop=self._loop)

    @asyncio.coroutine
    def _run_handler(self, coro):
        try:
            return (yield from coro)
        except asyncio.CancelledError:  # pragma: no cover
            raise  # The handler was cancelled, so let it propagate.
        except (EOFError, OSError):  # pragma: no cover
            pass  # The connection was closed, so ignore the error.
        except (DecodeError, CommandError, asyncio.TimeoutError) as ex:
            self._handle_expected_error(ex)
        except Exception as ex:
            self._handle_unexpected_error(ex)

    def _handle_expected_error(self, ex):
        self.logger.warning("Connection error from %s over NCP: %s", self.remote_hostname, ex)

    def _handle_unexpected_error(self, ex):
        self.logger.exception("Unexpected error from %s over NCP", self.remote_hostname)

    def create_handler(self, coro):
        return super().create_handler(self._run_handler(coro))

    # Packet reading.

    def _field_predicate(self, field):
        return True

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
                field = self._field_buffer.popleft()
                self.logger.debug(
                    "Received field %s %s from %s over NCP",
                    field.packet_type, field.name, self.remote_hostname
                )
                return field
            # Read some more fields.
            header_buf = yield from self._reader.readexactly(PACKET_HEADER_STRUCT.size)
            size_remaining, decode_packet_body = decode_packet_cps(header_buf)
            body_buf = yield from self._reader.readexactly(size_remaining)
            packet = decode_packet_body(body_buf)
            self.logger.debug("Received packet %s from %s over NCP", packet.type, self.remote_hostname)
            self._field_buffer.extend(filter(self._field_predicate, (
                Field(self, packet, field)
                for field
                in packet.fields
            )))
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
        encoded_packet = encode_packet(packet_type, self._gen_id(), datetime.now(tz=timezone.utc), CLIENT_ID, fields)
        self._writer.write(encoded_packet)
        self.logger.debug("Sent packet %s to %s over NCP", packet_type, self.remote_hostname)
        for field in fields:
            self.logger.debug("Sent field %s %s to %s over NCP", packet_type, field.name, self.remote_hostname)
        # Create an iterator of response fields.
        expected_fields = frozenset(
            (field.name, field.id)
            for field
            in fields
        )
        return Response(self, lambda field: (
            field.packet_type == packet_type and
            (field.name, field.id) in expected_fields
        ))

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
            FieldData(field_name, self._gen_id(), field_params)
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
        return self._send_packet(packet_type, [FieldData(field_name, self._gen_id(), params)])
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

        After calling this method, use :meth:`wait_closed` to wait for the connection to fully close.

        .. hint::

            If you use the connection as an *async context manager*, there's no need to call :meth:`Connection.close`
            manually.
        """
        super().close()
        # Close the connection.
        if not self.is_closing():
            try:
                self._writer.write_eof()
            except (EOFError, OSError):  # pragma: no cover
                # If the socket is already closed due to a connection error, we dont' really care.
                pass
            finally:
                self._writer.close()
            self.logger.debug("Disconnected from %s over NCP", self.remote_hostname)

    def wait_closed(self):
        """
        Waits for the connection to fully close.

        This method is a *coroutine*.

        .. important::

            Only call this method after first calling :meth:`close`.

        .. hint::

            If you use the connection as an *async context manager*, there's no need to call
            :meth:`Connection.wait_closed` manually.
        """
        return super().wait_closed()
