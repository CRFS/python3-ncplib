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
"""
from __future__ import annotations
import asyncio
import binascii
from functools import partial
from typing import Awaitable, Callable, Optional, Tuple, TypeVar
import logging
import ssl
import warnings
from ncplib.connection import DEFAULT_TIMEOUT, _wait_for, _decode_remote_timeout, _handle_tunnel_args, Connection, Field
from ncplib.http import RE_HTTP_REQUEST, decode_http_head
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


def _write_http_response(
    writer: asyncio.StreamWriter,
    status: bytes,
    headers: Tuple[Tuple[bytes, bytes], ...] = (),
) -> None:
    writer.write((
        b"HTTP/1.1 %s\r\n"
        b"%s"
        b"Server: python3-ncplib\r\n"
        b"\r\n"
    ) % (status, b"".join(b"%s: %s\r\n" % header for header in headers)))


async def _client_connected(
    client_connected: Callable[[Connection], Awaitable[None]],
    timeout: int,
    is_tunnel: bool,
    authenticate: Optional[Callable[[str, str], bool]],
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
) -> None:
    connection = _create_server_connecton(reader, writer, timeout)
    try:
        # Handle tunnel.
        if is_tunnel:
            (method, uri), headers = await _wait_for(decode_http_head(RE_HTTP_REQUEST, reader), timeout)
            if method.upper() != "CONNECT":  # pragma: no cover
                _write_http_response(writer, b"405 Method Not Allowed")
                return
            if uri != "ncp.service":  # pragma: no cover
                _write_http_response(writer, b"403 Forbidden")
                return
            # Handle authentication.
            if authenticate:
                try:
                    auth_method, auth_token = headers.get("Proxy-Authorization", "").split()
                    if auth_method.lower() != "basic":    # pragma: no cover
                        raise ValueError
                    username, password = binascii.a2b_base64(auth_token).decode().split(":")
                    if not authenticate(username, password):
                        raise ValueError
                except ValueError:
                    _write_http_response(writer, b"401 Unauthorized", (
                        (b"Proxy-Authenticate", b"Basic realm=\"CRFS RFeye Node\", charset=\"utf-8\""),
                    ))
            _write_http_response(writer, b"200 OK")
        # Handle handshake.
        connection.send("LINK", "HELO")
        # Read the hostname.
        field = await connection.recv_field("LINK", "CCRE")
        connection.remote_hostname = str(field.get("CIW", connection.remote_hostname))
        # Read the remote timeout.
        raw_remote_timeout = _decode_remote_timeout(field)
        remote_timeout = 0 if raw_remote_timeout == 0 else max(min(raw_remote_timeout, 60), 5)
        if raw_remote_timeout != remote_timeout:
            warnings.warn(NCPWarning(f"Changed connection timeout from {raw_remote_timeout} to {remote_timeout}"))
        # Complete handshake.
        connection.send("LINK", "SCAR", LINK=remote_timeout)
        await connection.recv_field("LINK", "CARE")
        connection.send("LINK", "SCON")
        # Start keep-alive packets.
        connection._apply_remote_timeout(remote_timeout)
        # Handle connection.
        await client_connected(connection)
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


async def start_server(
    client_connected: Callable[[Connection], Awaitable[None]],
    host: str = "0.0.0.0", port: Optional[int] = None, *,
    timeout: int = DEFAULT_TIMEOUT,
    start_serving: bool = True,
    ssl: Optional[ssl.SSLContext] = None,
    authenticate: Optional[Callable[[str, str], bool]] = None,
) -> asyncio.base_events.Server:
    """
    Creates and returns a new :class:`Server` on the given host and port.

    :param client_connected: A coroutine function taking a single :class:`Connection`
            argument representing the client connection. When the connection handler exits, the :class:`Connection`
            will automatically close. If the client closes the connection, the connection handler will exit.
    :param str host: The host to bind the server to.
    :param int port: The port to bind the server to.
    :param int timeout: The network timeout (in seconds). Applies to: creating server, receiving a packet, closing
        connection, closing server.
    :param bool start_serving: Causes the created server to start accepting connections immediately.
    :param ssl.SSLContext ssl: Start the server using an encrypted (TLS) connection.
    :param authenticate: A callable taking a username and password argument, returning True if the authentication is
        successful, and false if not. When present, authentication is mandatory.
    :return: The created :class:`Server`.
    :rtype: Server
    """
    port, is_tunnel = _handle_tunnel_args(port, bool(ssl), bool(authenticate))
    server = await _wait_for(asyncio.start_server(
        partial(_client_connected, client_connected, timeout, is_tunnel, authenticate),
        host=host, port=port,
        ssl=ssl,
        ssl_handshake_timeout=timeout if ssl else None,
        start_serving=start_serving,
    ), timeout)
    for s in server.sockets:
        logger.info("Listening on %s:%s over NCP", *s.getsockname()[:2])
    return server
