"""
Value types
===========

.. currentmodule:: ncplib

Overview
--------

NCP data types are mapped onto python types as follows:

=========== ================================================
NCP type    Python type
=========== ================================================
int32       :class:`int`
uint32      :class:`ncplib.uint`
string      :class:`str`
raw         :class:`bytes`
data int8   :class:`array.array(typecode="b") <array.array>`
data int16  :class:`array.array(typecode="h") <array.array>`
data int32  :class:`array.array(typecode="i") <array.array>`
data uint8  :class:`array.array(typecode="B") <array.array>`
data uint16 :class:`array.array(typecode="H") <array.array>`
data uint32 :class:`array.array(typecode="I") <array.array>`
=========== ================================================


API reference
-------------

.. autoclass:: uint
    :members:
"""
from __future__ import annotations

__all__ = (
    "uint",
)


# Type converters.

class uint(int):

    """
    An unsigned integer value.

    Python does not distinguish between signed and unsigned integers, but :term:`NCP` encodes them differently.
    Additionally, the binary encoding restricts the ranges of signed and unsigned integers:

    -   ``-2 ** 31 <= int32 <= 2 ** 31 - 1``
    -   ``0 <= uint32 <= 2 ** 32 - 1``

    To distinguish between ``int32`` and ``uint32`` in :term:`NCP parameter` values, wrap any :class:`int` values to be
    encoded as ``uint32`` in :class:`uint`.
    """

    __slots__ = ()
