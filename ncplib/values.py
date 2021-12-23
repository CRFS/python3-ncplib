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
i32         :class:`int`
u32         :class:`ncplib.u32`
i64         :class:`ncplib.i64`
u64         :class:`ncplib.u64`
f32         :class:`float`
f64         :class:`ncplib.f64`
string      :class:`str`
raw         :class:`bytes`
data i8     :class:`array.array(typecode="b") <array.array>`
data i16    :class:`array.array(typecode="h") <array.array>`
data i32    :class:`array.array(typecode="i") <array.array>`
data u8     :class:`array.array(typecode="B") <array.array>`
data u16    :class:`array.array(typecode="H") <array.array>`
data u32    :class:`array.array(typecode="I") <array.array>`
data u64    :class:`array.array(typecode="L") <array.array>`
data i64    :class:`array.array(typecode="l") <array.array>`
data f32    :class:`array.array(typecode="f") <array.array>`
data f64    :class:`array.array(typecode="d") <array.array>`
=========== ================================================


API reference
-------------

.. autoclass:: u32
    :members:

.. autoclass:: i64
    :members:

.. autoclass:: u64
    :members:

.. autoclass:: f64
    :members:
"""
from __future__ import annotations


# Type converters.

class u32(int):

    """
    A `u32` value.

    Wrap any :class:`int` values to be encoded as ``u32`` in :class:`u32`.
    """

    __slots__ = ()


class i64(int):

    """
    An `i64` value.

    Wrap any :class:`int` values to be encoded as ``i64`` in :class:`i64`.
    """

    __slots__ = ()


class u64(int):

    """
    A `u64` value.

    Wrap any :class:`int` values to be encoded as ``u64`` in :class:`u64`.
    """

    __slots__ = ()


class f64(float):

    """
    A `f64` value.

    Wrap any :class:`float` values to be encoded as ``f64`` in :class:`f64`.
    """

    __slots__ = ()
