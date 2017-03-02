"""
NCP application framework
=========================

.. currentmodule:: ncplib

:mod:`ncplib` provides a simple application framework for building NCP applications in a declarative manner.


Field handlers
--------------

Field handlers are coroutines that handle a specific incoming :class:`Field`.

For example, here is an application that defines a simple echo protocol.

.. code::

    import ncplib

    class EchoApplication(ncplib.Application):

        async def handle_field_LINK_ECHO(self, field):
            value = field.get("VAL")
            if not value:
                raise ncplib.BadRequest("VAL is required")
            field.send(VAL=value)

If a field handler raises :class:`BadRequest`, then the client will receive an erro reply.

.. important::

    Field handlers should not call :meth:`Connection.recv`, :meth:`Connection.recv_field`,
    :meth:`Response.recv` or :meth:`Response.recv_field`. They should not use the async iteration protocol on
    :class:`Connection` or :class:`Response`.



Daemons
-------

Daemons are coroutines that run in the background of the application.

For example, here is an application that defines a daemon for sending a ping packet every 10 seconds.

.. code::

    import asyncio
    import ncplib

    class PingApplication(ncplib.Application):

        async def run_ping(self):
            while not self.connection.is_closing():
                self.connection.send("LINK", "PING")
                await asyncio.sleep(10)

        async def handle_connect(self):
            await super().handle_connect()
            self.start_daemon(self.run_ping())


.. important::

    Daemons should not call :meth:`Connection.recv`, :meth:`Connection.recv_field`,
    :meth:`Response.recv` or :meth:`Response.recv_field`. They should not use the async iteration protocol on
    :class:`Connection` or :class:`Response`.


API reference
-------------

.. autoclass:: BadRequest
    :members:
"""
import asyncio
from ncplib.errors import ConnectionClosed, CommandError, BadRequest


__all__ = ("Application",)


class Application:

    """
    A framework for building NCP applications.

    .. important::

        Do not instantiate an Application directly. Pass it as ``client_connected`` to :func:`start_server`,
        :func:`run_app` or :func:`run_client`.

    .. attribute:: connection

        The :class:`Connection` used by this Application.
    """

    def __init__(self, connection):
        self.connection = connection
        self._daemons = set()

    # Daemons.

    def start_daemon(self, coro):
        """
        Starts a background task.
        """
        daemon = self.connection._loop.create_task(coro)
        self._daemons.add(daemon)
        daemon.add_done_callback(self._daemons.remove)
        return daemon

    # Handlers.

    @asyncio.coroutine
    def handle_connect(self):
        """
        Called when the connection is establed.

        Use this to set up any background daemons using :meth:`start_daemon`.
        """
        pass

    @asyncio.coroutine
    def handle_unknown_field(self, field):
        """
        Called when a field is encountered that doesn't match any other field handler.
        """
        pass

    @asyncio.coroutine
    def handle_disconnect(self):
        """
        Called when the connection is shut down.

        Use this to perform any cleanup. The connection may already be closed.
        """
        pass

    @asyncio.coroutine
    def _handle_field(self, field):
        # Look up the handler.
        handler = getattr(self, "handle_field_{packet_type}_{field_name}".format(
            packet_type=field.packet_type,
            field_name=field.name,
        ), self.handle_unknown_field)
        # Run the handler.
        try:
            yield from handler(field)
        except asyncio.CancelledError:  # pragma: no cover
            raise
        except BadRequest as ex:
            self.connection.logger.warning(
                "Error in field %s %s from %s over NCP: %s",
                field.packet_type, field.name, self.connection.remote_hostname, ex,
            )
            if self.connection._send_errors and not self.connection.is_closing():
                field.send(ERRO=ex.detail, ERRC=400)
        except Exception as ex:
            self.connection.logger.exception(
                "Server error in field %s %s from %s over NCP",
                field.packet_type, field.name, self.connection.remote_hostname,
            )
            if self.connection._send_errors and not self.connection.is_closing():
                field.send(ERRO="Server error", ERRC=500)

    @asyncio.coroutine
    def __iter__(self):
        try:
            # Run connect hook.
            yield from self.handle_connect()
            # Accept fields.
            while True:
                try:
                    field = yield from self.connection.recv()
                except ConnectionClosed:
                    break  # Connection closed gracefully.
                except CommandError as ex:
                    # Do not stop receiving fields on a command error. Just log it and continue.
                    self.connection.logger.warning(
                        "Command error from %s over NCP: %s",
                        self.connection.remote_hostname, ex,
                    )
                else:
                    self.start_daemon(self._handle_field(field))
        finally:
            # Shut down daemons.
            for daemon in self._daemons:
                daemon.cancel()
            if self._daemons:
                yield from asyncio.wait(self._daemons, loop=self.connection._loop)
            # All done.
            yield from self.handle_disconnect()

    __await__ = __iter__
