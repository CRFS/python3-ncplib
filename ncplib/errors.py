"""
Errors and warnings
===================

.. currentmodule:: ncplib

:term:`NCP` errors and warnings.


API reference
-------------

.. autoexception:: NCPError
    :members:

.. autoexception:: NetworkError
    :members:

.. autoexception:: NetworkTimeout
    :members:

.. autoexception:: ConnectionClosed
    :members:

.. autoexception:: CommandError
    :members:

.. autoexception:: DecodeError
    :members:

.. autoexception:: CommandWarning
    :members:

.. autoexception:: DecodeWarning
    :members:
"""
from __future__ import annotations
import asyncio
from contextlib import contextmanager
from typing import Generator, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from ncplib.connection import Field


__all__ = (
    "NCPError",
    "NetworkError",
    "NetworkTimeout",
    "ConnectionClosed",
    "CommandError",
    "DecodeError",
    "NCPWarning",
    "CommandWarning",
    "DecodeWarning",
)


class CommandMixin:

    field: Field
    detail: str
    code: int

    def __init__(self, field: Field, detail: str, code: int) -> None:
        super().__init__(f"{field.packet_type} {field.name} {detail!r} (code {code})")  # type: ignore
        self.field = field
        self.detail = detail
        self.code = code


@contextmanager
def _wrap_errors() -> Generator[None, None, None]:
    try:
        yield
    except asyncio.CancelledError:  # pragma: no cover
        raise  # Propagate cancels.
    except asyncio.TimeoutError as ex:  # pragma: no cover
        raise NetworkTimeout(ex)
    except OSError as ex:  # pragma: no cover
        raise NetworkError(ex)
    except asyncio.IncompleteReadError as ex:
        if len(ex.partial) == 0:
            raise ConnectionClosed("Connection closed")
        raise NetworkError(ex)  # pragma: no cover


# Errors.

class NCPError(Exception):

    """Base class for all exceptions thrown by :mod:`ncplib`."""


class NetworkError(NCPError):

    """
    Raised when an NCP :class:`Connection` cannot connect, or disconnects unexpectedly.
    """


class NetworkTimeout(NetworkError, asyncio.TimeoutError):

    """
    Raised when an NCP :class:`Connection` times out while performing network activity.
    """


class ConnectionClosed(NCPError):

    """
    Raised when an NCP :class:`Connection` is closed gracefully.
    """


class CommandError(CommandMixin, NCPError):

    """
    Raised by the :doc:`client` when the :doc:`server` sends a :term:`NCP field` containing an ``ERRO`` parameter.

    Can be disabled by setting ``auto_erro`` to :obj:`False` in :func:`ncplib.connect`.

    .. attribute:: field

        The :class:`ncplib.Field` that triggered the error.

    .. attribute:: detail

        The human-readable :class:`str` message from the server.

    .. attribute:: code

        The :class:`int` code from the server,
    """


class DecodeError(NCPError):

    """
    Raised when a non-recoverable error was encountered in a :term:`NCP packet`.
    """


# Warnings.

class NCPWarning(Warning):

    """Base class for all warnings raised by :mod:`ncplib`."""


class CommandWarning(CommandMixin, NCPWarning):

    """
    Issued by the :doc:`client` when the :doc:`server` sends a :term:`NCP field` containing a ``WARN`` parameter.

    Can be disabled by setting ``auto_warn`` to :obj:`False` in :func:`ncplib.connect`.

    .. attribute:: field

        The :class:`ncplib.Field` that triggered the error.

    .. attribute:: detail

        The human-readable :class:`str` message from the server.

    .. attribute:: code

        The :class:`int` code from the server,
    """


class DecodeWarning(NCPWarning):

    """
    Issued when a recoverable error was encountered in a :term:`NCP packet`.
    """
