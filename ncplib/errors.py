"""
Errors and warnings
===================

.. currentmodule:: ncplib

:term:`NCP` errors and warnings.


API reference
-------------

.. autoexception:: NCPError
    :members:

.. autoexception:: ConnectionError
    :members:

.. autoexception:: ConnectionClosed
    :members:

.. autoexception:: CommandError
    :members:

.. autoexception:: DecodeError
    :members:

.. autoclass:: Application
    :members:

.. autoexception:: CommandWarning
    :members:

.. autoexception:: DecodeWarning
    :members:
"""


__all__ = (
    "NCPError",
    "ConnectionError",
    "ConnectionClosed",
    "CommandError",
    "DecodeError",
    "BadRequest",
    "NCPWarning",
    "CommandWarning",
    "DecodeWarning",
)


class CommandMixin:

    """
    .. attribute:: field

        The :class:`ncplib.Field` that triggered the error.

    .. attribute:: detail

        The human-readable :class:`str` message from the server.

    .. attribute:: code

        The :class:`int` code from the server,
    """

    def __init__(self, field, detail, code):
        super().__init__("{packet_type} {field_name} {detail!r} (code {code})".format(
            packet_type=field.packet_type,
            field_name=field.name,
            detail=detail,
            code=code,
        ))
        self.field = field
        self.detail = detail
        self.code = code


# Errors.

class NCPError(Exception):

    """Base class for all exceptions thrown by :mod:`ncplib`."""


class ConnectionError(NCPError):

    """
    Raised when an NCP :class:`Connection` cannot connect, or disconnects unexpectedly.
    """


class ConnectionClosed(NCPError):

    """
    Raised when an NCP :class:`Connection` is closed gracefully.
    """


class CommandError(CommandMixin, NCPError):

    """
    Raised by the :doc:`client` when the :doc:`server` sends a :term:`NCP field` containing an ``ERRO`` parameter.

    Can be disabled by setting ``auto_erro`` to :obj:`False` in :func:`ncplib.connect`.

    """
    __doc__ += CommandMixin.__doc__


class DecodeError(NCPError):

    """
    Raised when a non-recoverable error was encountered in a :term:`NCP packet`.
    """


class BadRequest(NCPError):

    """
    An error that can be thrown in a field handler to signal a problem in handling the request.
    """

    def __init__(self, detail, code=400):
        super().__init__("{detail!r} (code {code})".format(detail=detail, code=code))
        self.detail = detail
        self.code = code


# Warnings.

class NCPWarning(Warning):

    """Base class for all warnings raised by :mod:`ncplib`."""


class CommandWarning(CommandMixin, NCPWarning):

    """
    Issued by the :doc:`client` when the :doc:`server` sends a :term:`NCP field` containing a ``WARN`` parameter.

    Can be disabled by setting ``auto_warn`` to :obj:`False` in :func:`ncplib.connect`.

    """
    __doc__ += CommandMixin.__doc__


class DecodeWarning(NCPWarning):

    """
    Issued when a recoverable error was encountered in a :term:`NCP packet`.
    """
