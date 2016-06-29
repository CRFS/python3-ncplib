"""
Errors and warnings
===================

.. currentmodule:: ncplib

:term:`NCP` errors and warnings.


API reference
-------------

.. autoexception:: CommandError
    :members:

.. autoexception:: CommandWarning
    :members:

.. autoexception:: DecodeError
    :members:

.. autoexception:: DecodeWarning
    :members:
"""


__all__ = (
    "CommandError",
    "CommandWarning",
    "DecodeError",
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
        super().__init__("{packet_type} {field_name} '{detail}' (code {code})".format(
            packet_type=field.packet_type,
            field_name=field.name,
            detail=detail,
            code=code,
        ))
        self.field = field
        self.detail = detail
        self.code = code


# Errors.

class CommandError(CommandMixin, Exception):

    """
    Raised by the :doc:`client` when the :doc:`server` sends a :term:`NCP field` containing an ``ERRO`` parameter.

    Can be disabled by setting ``auto_erro`` to :obj:`False` in :func:`ncplib.connect`.
    """
    __doc__ += CommandMixin.__doc__


class DecodeError(Exception):

    """
    Raised when a non-recoverable error was encountered in a :term:`NCP packet`.
    """


# Warnings.

class CommandWarning(CommandMixin, Warning):

    """
    Issued by the :doc:`client` when the :doc:`server` sends a :term:`NCP field` containing a ``WARN`` parameter.

    Can be disabled by setting ``auto_warn`` to :obj:`False` in :func:`ncplib.connect`.
    """
    __doc__ += CommandMixin.__doc__


class DecodeWarning(Warning):

    """
    Issued when a recoverable error was encountered in a :term:`NCP packet`.
    """
