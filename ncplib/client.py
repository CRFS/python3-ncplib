"""
NCP client
==========

.. currentmodule:: ncplib

:mod:`ncplib` allows you to connect to a :doc:`server` and issue commands.


Overview
--------

Connecting to a NCP server
^^^^^^^^^^^^^^^^^^^^^^^^^^

Connect to a :doc:`server` using :func:`connect`. The returned :class:`Connection` will automatically close when the
connection block exits.

.. code:: python

    import ncplib

    async with await ncplib.connect("127.0.0.1", 9999) as connection:
        pass  # Your client code here.

    # Connection is automatically closed here.


Sending a packet
^^^^^^^^^^^^^^^^

Send a :term:`NCP packet` containing a single :term:`NCP field` using :meth:`Connection.send`:

.. code:: python

    response = connection.send("DSPC", "TIME", SAMP=1024, FCTR=1200)


Receiving replies to a packet
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The return value of :meth:`Connection.send` is a :class:`Response`. Receive a single :term:`NCP field` reply using
:meth:`Response.recv`:

.. code:: python

    field = await response.recv()

Alternatively, use the :class:`Response` as an *async iterator* to loop over multiple :term:`NCP field` replies:

.. code:: python

    async for field in response:
        pass

.. important::
    The *async for loop* will only terminate when the underlying connection closes.


Accessing field data
^^^^^^^^^^^^^^^^^^^^

The return value of :meth:`Response.recv` is a :class:`Field`, representing a :term:`NCP field`. Access contained
:term:`NCP parameters <NCP parameter>` using item access:

.. code:: python

    print(field["TSDC"])


Advanced usage
^^^^^^^^^^^^^^

-   :doc:`NCP connection documentation <connection>`.


API reference
-------------

.. autofunction:: connect
"""
from __future__ import annotations
import asyncio
import binascii
from functools import partial
import logging
import platform
import ssl
from typing import Optional
import warnings
from ncplib.connection import DEFAULT_TIMEOUT, _wait_for, _decode_remote_timeout, _handle_tunnel_args, Connection, Field
from ncplib.errors import AuthenticationError, NetworkError, CommandError, CommandWarning, NCPWarning
from ncplib.http import RE_HTTP_STATUS, decode_http_head


logger = logging.getLogger(__name__)


def _client_predicate(field: Field, *, auto_erro: bool, auto_warn: bool, auto_ackn: bool) -> bool:
    if auto_erro:
        error_detail = field.get("ERRO")
        error_code = field.get("ERRC")
        if error_detail is not None or error_code is not None:
            raise CommandError(field, error_detail, error_code)  # type: ignore
        # Ignore the rest of packet-level errors.
        if field.name == "ERRO":  # pragma: no cover
            return False
    # Handle warnings.
    if auto_warn:
        warning_detail = field.get("WARN")
        warning_code = field.get("WARC")
        if warning_detail is not None or warning_code is not None:
            warnings.warn(CommandWarning(field, warning_detail, warning_code))  # type: ignore
        # Ignore the rest of packet-level warnings.
        if field.name == "WARN":  # pragma: no cover
            return False
    # Handle acks.
    return not auto_ackn or "ACKN" not in field


async def connect(
    host: str, port: Optional[int] = None, *,
    remote_hostname: Optional[str] = None,
    hostname: Optional[str] = None,
    timeout: int = DEFAULT_TIMEOUT,
    auto_erro: bool = True,
    auto_warn: bool = True,
    auto_ackn: bool = True,
    ssl: bool | ssl.SSLContext = False,
    username: str = "",
    password: str = "",
) -> Connection:
    """
    Connects to a :doc:`server`.

    :param str host: The hostname of the :doc:`server`. This can be an IP address or domain name.
    :param int port: The port number of the :doc:`server`.
    :param str remote_hostname: The identifying hostname for the remote end of the connection. If omitted, this will
        be the host:port of the NCP server.
    :param str hostname: The identifying hostname in the client connection. Defaults to the system hostname.
    :param int timeout: The network timeout (in seconds). Applies to: connecting, receiving a packet, closing
        connection.
    :param bool auto_erro: Automatically raise a :exc:`CommandError` on receiving an ``ERRO`` :term:`NCP parameter`.
    :param bool auto_warn: Automatically issue a :exc:`CommandWarning` on receiving a ``WARN`` :term:`NCP parameter`.
    :param bool auto_ackn: Automatically ignore :term:`NCP fields <NCP field>` containing an ``ACKN``
        :term:`NCP parameter`.
    :param bool ssl: Connect to the Node using an encrypted (TLS) connection. Requires TLS support on the Node.
    :param str username: Authenticate with the Node using the given username. Requires authentication support on the
        Node.
    :param str password: Authenticate with the Node using the given password. Requires authentication support on the
        Node.
    :raises ncplib.NCPError: if the NCP connection failed.
    :return: The client :class:`Connection`.
    :rtype: Connection
    """
    assert timeout > 0, "timeout must be greater than 0"
    port, is_tunnel = _handle_tunnel_args(port, bool(ssl), bool(username or password))
    # Create the network connection.
    reader, writer = await _wait_for(asyncio.open_connection(
        host, port,
        ssl=ssl,
        ssl_handshake_timeout=timeout if ssl else None,
    ), timeout)
    # Connect via HTTP tunnel.
    if is_tunnel:
        writer.write((
            b"CONNECT ncp.service HTTP/1.1\r\n"
            b"Proxy-Authorization: Basic %s\r\n"
            b"\r\n"
        ) % binascii.b2a_base64(f"{username}:{password}".encode(), newline=False))
        # Check authentication success.
        (status, message), _ = await _wait_for(decode_http_head(RE_HTTP_STATUS, reader), timeout)
        if status == "401":
            raise AuthenticationError(f"HTTP {status} {message}")
        elif status != "200":  # pragma: no cover
            raise NetworkError(f"HTTP {status} {message}")
    # Create the NCP connection.
    connection = Connection(
        reader, writer, partial(_client_predicate, auto_erro=auto_erro, auto_warn=auto_warn, auto_ackn=auto_ackn),
        logger=logger,
        remote_hostname=f"{host}:{port}" if remote_hostname is None else remote_hostname,
        timeout=timeout,
    )
    # Handle auth.
    try:
        hostname = hostname or platform.node() or "python3-ncplib"
        # Read the initial LINK HELO packet.
        await connection.recv_field("LINK", "HELO")
        # Send the connection request.
        connection.send("LINK", "CCRE", CIW=hostname, LINK=timeout)
        # Read the connection response packet.
        remote_timeout = _decode_remote_timeout(await connection.recv_field("LINK", "SCAR"))
        # Send the auth request packet.
        connection.send("LINK", "CARE", CAR=hostname)
        # Read the auth response packet.
        await connection.recv_field("LINK", "SCON")
    except BaseException:
        connection.close()
        await connection.wait_closed()
        raise
    # Start keep-alive packets.
    if remote_timeout != 0 and remote_timeout != timeout:
        warnings.warn(NCPWarning(f"Server changed connection timeout to {remote_timeout}"))
    connection._apply_remote_timeout(remote_timeout)
    # All done!
    return connection
