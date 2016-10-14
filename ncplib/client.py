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

import asyncio
import logging
import warnings
from ncplib.connection import Connection
from ncplib.errors import CommandError, CommandWarning


__all__ = (
    "connect",
    "Client",
)


logger = logging.getLogger(__name__)


AUTH_ID = "python3-ncplib"


class Client(Connection):

    def __init__(self, host, port, reader, writer, *, loop, auto_auth, auto_erro, auto_warn, auto_ackn):
        super().__init__(host, port, reader, writer, logger, loop=loop)
        # PacketData handling.
        self._auto_auth = auto_auth
        self._auto_erro = auto_erro
        self._auto_warn = auto_warn
        self._auto_ackn = auto_ackn

    # Connection lifecycle.

    async def _handle_auth(self):
        # Read the initial LINK HELO packet.
        await self.recv_field("LINK", "HELO")
        # Send the connection request.
        self.send("LINK", "CCRE", CIW=AUTH_ID)
        # Read the connection response packet.
        await self.recv_field("LINK", "SCAR")
        # Send the auth request packet.
        self.send("LINK", "CARE", CAR=AUTH_ID)
        # Read the auth response packet.
        await self.recv_field("LINK", "SCON")

    async def _connect(self):
        # Auto-authenticate.
        if self._auto_auth:
            await self._handle_auth()
        # All done.
        self.logger.info("Connected")

    # Receiving fields.

    def _handle_erro(self, field):
        error_detail = field.get("ERRO", None)
        error_code = field.get("ERRC", None)
        if error_detail is not None or error_code is not None:
            raise CommandError(field, error_detail, error_code)
        # Ignore the rest of packet-level errors.
        return field.name != "ERRO"

    def _handle_warn(self, field):
        warning_detail = field.get("WARN", None)
        warning_code = field.get("WARC", None)
        if warning_detail is not None or warning_code is not None:
            warnings.warn(CommandWarning(field, warning_detail, warning_code))
        # Ignore the rest of packet-level warnings.
        return field.name != "WARN"

    def _handle_ackn(self, field):
        return "ACKN" not in field

    def _field_predicate(self, field):
        return (
            # Handle errors.
            (not self._auto_erro or self._handle_erro(field)) and
            # Handle warnings.
            (not self._auto_warn or self._handle_warn(field)) and
            # Handle acks.
            (not self._auto_ackn or self._handle_ackn(field))
        )


async def connect(host, port=9999, *, loop=None, auto_auth=True, auto_erro=True, auto_warn=True, auto_ackn=True):
    """
    Connects to a :doc:`server`.

    This function is a *coroutine*.

    :param str host: The hostname of the :doc:`server`. This can be an IP address or domain name.
    :param int port: The port number of the :doc:`server`.
    :param asyncio.BaseEventLoop loop: The event loop. Defaults to the default asyncio event loop.
    :param bool auto_auth: Automatically perform the :term:`NCP` authentication handshake on connect.
    :param bool auto_erro: Automatically raise a :exc:`CommandError` on receiving an ``ERRO`` :term:`NCP parameter`.
    :param bool auto_warn: Automatically issue a :exc:`CommandWarning` on receiving a ``WARN`` :term:`NCP parameter`.
    :param bool auto_ackn: Automatically ignore :term:`NCP fields <NCP field>` containing an ``ACKN``
        :term:`NCP parameter`.
    :return: The client :class:`Connection`.
    :rtype: Connection
    """
    reader, writer = await asyncio.open_connection(host, port, loop=loop)
    client = Client(
        host,
        port,
        reader,
        writer,
        loop=loop,
        auto_auth=auto_auth,
        auto_erro=auto_erro,
        auto_warn=auto_warn,
        auto_ackn=auto_ackn,
    )
    try:
        await client._connect()
    except:
        client.close()
        raise
    return client
