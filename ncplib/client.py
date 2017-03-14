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

.. autofunction:: run_client
"""

import asyncio
from functools import partial
import logging
import platform
import warnings
from ncplib.compat import wait_for
from ncplib.connection import Connection
from ncplib.errors import NCPError, CommandError, CommandWarning, ConnectionError


__all__ = (
    "connect",
    "run_client",
)


logger = logging.getLogger(__name__)


def _client_predicate(field, *, auto_erro, auto_warn, auto_ackn):
    if auto_erro:
        error_detail = field.get("ERRO")
        error_code = field.get("ERRC")
        if error_detail is not None or error_code is not None:
            raise CommandError(field, error_detail, error_code)
        # Ignore the rest of packet-level errors.
        if field.name == "ERRO":  # pragma: no cover
            return False
    # Handle warnings.
    if auto_warn:
        warning_detail = field.get("WARN")
        warning_code = field.get("WARC")
        if warning_detail is not None or warning_code is not None:
            warnings.warn(CommandWarning(field, warning_detail, warning_code))
        # Ignore the rest of packet-level warnings.
        if field.name == "WARN":  # pragma: no cover
            return False
    # Handle acks.
    return not auto_ackn or "ACKN" not in field


def _get_remote_hostname(host, port, remote_hostname):
    return "{host}:{port}".format(host=host, port=port) if remote_hostname is None else remote_hostname


@asyncio.coroutine
def _connect(
    host, port, *,
    loop,
    auto_link,
    auto_auth,
    auto_erro,
    auto_warn,
    auto_ackn,
    remote_hostname,
    hostname
):
    loop = loop or asyncio.get_event_loop()
    hostname = hostname or platform.node() or "python3-ncplib" if auto_auth else None
    # Create the network connection.
    try:
        reader, writer = yield from asyncio.open_connection(host, port, loop=loop)
    except OSError as ex:  # pragma: no cover
        raise ConnectionError(ex)

    connection = Connection(
        reader, writer, partial(_client_predicate, auto_erro=auto_erro, auto_warn=auto_warn, auto_ackn=auto_ackn),
        loop=loop,
        logger=logger,
        remote_hostname=remote_hostname,
        auto_link=auto_link,
        send_errors=False,
    )
    # Handle auto auth.
    try:
        if auto_auth:
            # Read the initial LINK HELO packet.
            yield from connection.recv_field("LINK", "HELO")
            # Send the connection request.
            connection.send("LINK", "CCRE", CIW=hostname)
            # Read the connection response packet.
            yield from connection.recv_field("LINK", "SCAR")
            # Send the auth request packet.
            connection.send("LINK", "CARE", CAR=hostname)
            # Read the auth response packet.
            yield from connection.recv_field("LINK", "SCON")
    except:
        connection.close()
        raise
    # All done!
    connection._start_tasks()
    return connection


_connect_args = """:param str host: The hostname of the :doc:`server`. This can be an IP address or domain name.
    :param int port: The port number of the :doc:`server`.
    :param asyncio.BaseEventLoop loop: The event loop. Defaults to the default asyncio event loop.
    :param bool auto_link: Automatically send periodic LINK packets over the connection.
    :param bool auto_auth: Automatically perform the :term:`NCP` authentication handshake on connect.
    :param bool auto_erro: Automatically raise a :exc:`CommandError` on receiving an ``ERRO`` :term:`NCP parameter`.
    :param bool auto_warn: Automatically issue a :exc:`CommandWarning` on receiving a ``WARN`` :term:`NCP parameter`.
    :param bool auto_ackn: Automatically ignore :term:`NCP fields <NCP field>` containing an ``ACKN``
        :term:`NCP parameter`.
    :param string remote_hostname: The identifying hostname for the remote end of the connection. If omitted, this will
        be the host:port of the NCP server.
    :param string hostname: The identifying hostname in the client connection. Only applies when ``auto_auth`` is
        enabled. Defaults to the system hostname.
    """


def connect(
    host, port=9999, *,
    loop=None,
    auto_link=True,
    auto_auth=True,
    auto_erro=True,
    auto_warn=True,
    auto_ackn=True,
    remote_hostname=None,
    hostname=None
):
    """
    Connects to a :doc:`server`.

    This function is a *coroutine*.

    """
    return _connect(
        host, port,
        loop=loop,
        auto_link=auto_link,
        auto_auth=auto_auth,
        auto_erro=auto_erro,
        auto_warn=auto_warn,
        auto_ackn=auto_ackn,
        remote_hostname=_get_remote_hostname(host, port, remote_hostname),
        hostname=hostname,
    )


connect.__doc__ += _connect_args + """:raises ncplib.NCPError: if the NCP connection failed.
    :return: The client :class:`Connection`.
    :rtype: Connection
    """


@asyncio.coroutine
def run_client(
    client_connected,
    host, port=9999, *,
    loop=None,
    auto_link=True,
    auto_auth=True,
    auto_erro=True,
    auto_warn=True,
    auto_ackn=True,
    remote_hostname=None,
    hostname=None,
    connect_timeout=15
):
    """
    Connects to a :doc:`server` and runs a callback coroutine on the connection.

    This function is a *coroutine*.

    This coroutine will run until the connection closes. Errors from the client are logger, but not raised, and this
    function will always return ``None``.

    :param int connect_timeout: The time to wait while establishing a client connection.
    """
    loop = loop or asyncio.get_event_loop()
    remote_hostname = _get_remote_hostname(host, port, remote_hostname)
    try:
        # Connect to the server.
        try:
            connection = yield from wait_for(_connect(
                host, port,
                loop=loop,
                auto_link=auto_link,
                auto_auth=auto_auth,
                auto_erro=auto_erro,
                auto_warn=auto_warn,
                auto_ackn=auto_ackn,
                remote_hostname=remote_hostname,
                hostname=hostname,
            ), connect_timeout, loop=loop)
        except (asyncio.TimeoutError, NCPError) as ex:
            logger.warning(
                "Could not connect to %s over NCP: %s", remote_hostname,
                "Timeout" if isinstance(ex, asyncio.TimeoutError) else ex,
            )
            return
        # Run the app.
        try:
            yield from client_connected(connection)
        except NCPError as ex:  # Warnings on client error.
            logger.warning("Connection error from %s over NCP: %s", remote_hostname, ex)
        finally:
            connection.close()
    except asyncio.CancelledError:  # pragma: no cover
        raise
    except Exception as ex:  # pragma: no cover
        logger.exception("Unexpected error from %s over NCP", remote_hostname, exc_info=ex)


run_client.__doc__ += _connect_args
