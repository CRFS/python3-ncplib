"""
NCP server
==========

.. currentmodule:: ncplib

:mod:`ncplib` allows you to create a NCP server and respond to incoming :doc:`client` connections.


Overview
--------

Defining a connection handler
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

A connection handler is a coroutine that starts whenever a new :doc:`client` connects to the server. The provided
:class:`Connection` allows you to receive incoming NCP commands as :class:`Field` instances.

.. code:: python

    async def client_connected(connection):
        pass

When the connection handler exits, the :class:`Connection` will automatically close.


Listening for an incoming packet
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

When writing a :doc:`server`, you most likely want to wait for the connected client to execute a command. Within your
``client_connected`` function, Listen for an incomining :term:`NCP field` using :meth:`Connection.recv`.

.. code:: python

    field = await connection.recv()

Alternatively, use the :class:`Connection` as an *async iterator* to loop over multiple :term:`NCP field` replies:

.. code:: python

    async for field in connection:
        pass

.. important::
    The *async for loop* will only terminate when the underlying connection closes.


Accessing field data
^^^^^^^^^^^^^^^^^^^^

The return value of :meth:`Connection.recv` is a :class:`Field`, representing a :term:`NCP field`.

Access information about the :term:`NCP field` and enclosing :term:`NCP packet`:

.. code:: python

    print(field.packet_type)
    print(field.name)

Access contained :term:`NCP parameters <NCP parameter>` using item access:

.. code:: python

    print(field["FCTR"])


Replying to the incoming field
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Send a reply to an incoming :class:`Field` using :meth:`Field.send`.

.. code:: python

    field.send(ACKN=1)


Putting it all together
^^^^^^^^^^^^^^^^^^^^^^^

A simple ``client_connected`` callback might like this:

.. code:: python

    async def client_connected(connection):
        async for field in connection:
            if field.packet_type == "DSPC" and field.name == "TIME":
                field.send(ACNK=1)
                # Do some more command processing here.
            else:
                field.send(ERRO="Unknown command", ERRC=400)
                break


Start the server
^^^^^^^^^^^^^^^^

Start a new NCP server.

.. code:: python

    loop = asyncio.get_event_loop()
    server = loop.run_until_complete(_start_server(client_connected))
    try:
        loop.run_forever()
    finally:
        server.close()
        loop.run_until_complete(server.wait_closed())


Advanced usage
^^^^^^^^^^^^^^

-   :doc:`NCP connection documentation <connection>`.


API reference
-------------

.. autofunction:: start_server

.. autoclass:: Server
    :members:
"""
from __future__ import annotations
import asyncio
from types import TracebackType
from typing import Awaitable, Callable, Optional, Sequence, Type, TypeVar
import logging
from socket import socket
import warnings
from ncplib.connection import DEFAULT_TIMEOUT, _wait_for, _decode_remote_timeout, Connection, Field
from ncplib.errors import NCPError, NCPWarning


T = TypeVar("T")


logger = logging.getLogger(__name__)


def _server_predicate(field: Field) -> bool:
    return True


def _create_server_connecton(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, timeout: int) -> Connection:
    return Connection(
        reader, writer, _server_predicate,
        logger=logger,
        remote_hostname=":".join(map(str, writer.get_extra_info("peername")[:2])),
        timeout=timeout,
    )


class Server:

    """
    A :doc:`server`.

    Servers can be used as *async context managers* to automatically shut down the server:

    .. code:: python

        async with server:
            pass

        # Server is automatically shut down.

    .. important::

        Do not instantiate this class directly. Use :func:`start_server` to create a :class:`Server`.
    """

    _client_connected: Callable[[Connection], Awaitable[None]]
    _host: str
    _port: int
    _timeout: int

    def __init__(
        self, client_connected: Callable[[Connection], Awaitable[None]], host: str, port: int, *,
        timeout: int,
    ):
        self._client_connected = client_connected  # type: ignore
        self._host = host
        self._port = port
        # Config.
        self._timeout = timeout

    async def _run_client_connected(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        connection = _create_server_connecton(reader, writer, self._timeout)
        try:
            # Handle auth.
            connection.send("LINK", "HELO")
            # Read the hostname.
            field = await connection.recv_field("LINK", "CCRE")
            connection.remote_hostname = str(field.get("CIW", connection.remote_hostname))
            # Read the remote timeout.
            raw_remote_timeout = _decode_remote_timeout(field)
            remote_timeout = 0 if raw_remote_timeout == 0 else max(min(raw_remote_timeout, 60), 5)
            if raw_remote_timeout != remote_timeout:
                warnings.warn(NCPWarning(f"Changed connection timeout from {raw_remote_timeout} to {remote_timeout}"))
            # Complete authentication.
            connection.send("LINK", "SCAR", LINK=remote_timeout)
            await connection.recv_field("LINK", "CARE")
            connection.send("LINK", "SCON")
            # Start keep-alive packets.
            connection._apply_remote_timeout(remote_timeout)
            # Handle connection.
            await self._client_connected(connection)  # type: ignore
        # Close the connection.
        except asyncio.CancelledError:  # pragma: no cover
            raise  # Propagate cancels, not needed in Python3.8+.
        except NCPError as ex:  # Warnings on client decode error.
            logger.warning("Connection error from %s over NCP: %s", connection.remote_hostname, ex)
            if not connection.is_closing():
                connection.send("LINK", "ERRO", ERRO="Bad request", ERRC=400)
        except Exception as ex:
            logger.exception("Unexpected error from %s over NCP", connection.remote_hostname, exc_info=ex)
            if not connection.is_closing():
                connection.send("LINK", "ERRO", ERRO="Server error", ERRC=500)
        finally:
            connection.close()
            try:
                await connection.wait_closed()
            except NCPError as ex:  # pragma: no cover
                logger.warning("Connection error from %s over NCP: %s", connection.remote_hostname, ex)

    async def _connect(self) -> None:
        self._server = await _wait_for(
            asyncio.start_server(self._run_client_connected, self._host, self._port),
            self._timeout,
        )
        for s in self.sockets:
            logger.info("Listening on %s:%s over NCP", *s.getsockname()[:2])

    @property
    def sockets(self) -> Sequence[socket]:
        """
        A list of the connected listening sockets.
        """
        return self._server.sockets

    def close(self) -> None:
        """
        Shuts down the server.

        After calling this method, use :meth:`wait_closed` to wait for the server to fully shut down.

        .. hint::

            If you use the server as an *async context manager*, there's no need to call :meth:`Server.close`
            manually.
        """
        self._server.close()

    async def wait_closed(self) -> None:
        """
        Waits for the server to fully shut down.

        .. important::

            Only call this method after first calling :meth:`close`.

        .. hint::

            If you use the server as an *async context manager*, there's no need to call
            :meth:`Server.wait_closed` manually.
        """
        await _wait_for(self._server.wait_closed(), self._timeout)

    async def __aenter__(self) -> "Server":
        return self

    async def __aexit__(self, exc_type: Optional[Type[T]], exc: Optional[T], tb: Optional[TracebackType]) -> None:
        self.close()
        await self.wait_closed()


async def start_server(
    client_connected: Callable[[Connection], Awaitable[None]],
    host: str = "0.0.0.0", port: int = 9999, *,
    timeout: int = DEFAULT_TIMEOUT,
) -> Server:
    """
    Creates and returns a new :class:`Server` on the given host and port.

    :param client_connected: A coroutine function taking a single :class:`Connection`
            argument representing the client connection. When the connection handler exits, the :class:`Connection`
            will automatically close. If the client closes the connection, the connection handler will exit.
    :param str host: The host to bind the server to.
    :param int port: The port to bind the server to.
    :param int timeout: The network timeout (in seconds). Applies to: creating server, receiving a packet, closing
        connection, closing server.
    :return: The created :class:`Server`.
    :rtype: Server
    """
    server = Server(client_connected, host, port, timeout=timeout)
    await server._connect()
    return server
