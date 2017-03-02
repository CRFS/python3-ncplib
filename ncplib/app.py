"""
NCP application helpers
=======================

.. currentmodule:: ncplib

An application consists of a number of daemons and field handlers.

Define field handlers by subclassing :class:`Application` and defining methods with the signature
``handle_field_PACK_FIEL(self, field)``, where ``PACK`` is the :attr:`Field.packet_type` and ``FIEL`` is the
``Field.packet_name``. Field handlers can report errors by raising a :class:`BadRequest`.

Start daemons using :meth:`Application.start_daemon`.

.. important::

    Daemons and field handlers should not call :meth:`Connection.recv`, :meth:`Connection.recv_field`,
    :meth:`Response.recv` or :meth:`Response.recv_field`. They should not use the async iteration protocol on
    :class:`Connection` or :class:`Response`. They should only send fields using :meth:`Connection.send` or
    :meth:`Field.send`.


API reference
-------------

.. autoclass:: BadRequest
    :members:

.. autoclass:: Application
    :members:
"""
import asyncio


__all__ = ("BadRequest", "Application",)


class BadRequest(Exception):

    """
    An error that can be thrown in a field handler to signal a problem in handling the request.
    """

    def __init__(self, detail, code=400):
        super().__init__("{detail!r} (code {code})".format(detail=detail, code=code))
        self.detail = detail
        self.code = code


class Application:

    """
    A helper for building NCP applications.
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

        Use this to set up any background daemons using :meth:`create_deamon`.
        """
        pass

    @asyncio.coroutine
    def _handle_field(self, field):
        # Look up the handler.
        try:
            handler = getattr(self, "handle_field_{packet_type}_{field_name}".format(
                packet_type=field.packet_type,
                field_name=field.name,
            ))
        except AttributeError:  # pragma: no cover
            return  # Unknown field, ignore.
        # Run the handler.
        try:
            yield from handler(field)
        except BadRequest as ex:
            self.connection.logger.warning(
                "Error in field %s %s from %s over NCP: %s",
                field.packet_type, field.name, self.connection.remote_hostname, ex,
            )
            field.send(ERRO=ex.detail, ERRC=400)
        except Exception:
            self.connection.logger.exception(
                "Server error in field %s %s from %s over NCP",
                field.packet_type, field.name, self.connection.remote_hostname,
            )
            field.send(ERRO="Server error", ERRC=500)

    def __iter__(self):
        try:
            # Run connect hook.
            yield from self.handle_connect()
            # Accept fields.
            while not self.connection.is_closing():
                field = yield from self.connection.recv()
                self.start_daemon(self._handle_field(field))
        finally:
            # Shut down daemons.
            for daemon in self._daemons:
                daemon.cancel()
            if self._daemons:
                yield from asyncio.wait(self._daemons, loop=self._loop)

    __await__ = __iter__
