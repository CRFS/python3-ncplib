"""
ncplib
======

:term:`NCP` library for Python 3, developed by `CRFS`_.

.. image:: https://github.com/CRFS/python3-ncplib/workflows/Python%20package/badge.svg
    :target: https://github.com/CRFS/python3-ncplib


Features
--------

-   :doc:`client`.
-   :doc:`server`.
-   Asynchronous connections via :mod:`asyncio`.


Resources
---------

-   `Documentation`_ is on Read the Docs.
-   `Examples`_, `issue tracking`_ and `source code`_ are on GitHub.


Usage
-----

.. toctree::
    :maxdepth: 1

    installation
    client
    server
    connection
    errors
    values


More information
----------------

.. toctree::
    :maxdepth: 1

    contributing
    glossary
    changelog


.. include:: /_include/links.rst
"""


from ncplib.client import connect as connect  # noqa
from ncplib.connection import Connection as Connection, Response as Response, Field as Field  # noqa
from ncplib.errors import (  # noqa
    NCPError as NCPError,
    NetworkError as NetworkError,
    AuthenticationError as AuthenticationError,
    NetworkTimeoutError as NetworkTimeoutError,
    ConnectionClosed as ConnectionClosed,
    CommandError as CommandError,
    DecodeError as DecodeError,
    NCPWarning as NCPWarning,
    CommandWarning as CommandWarning,
    DecodeWarning as DecodeWarning,
)
from ncplib.server import start_server as start_server  # noqa
from ncplib.values import u32 as u32, i64 as i64, u64 as u64, f64 as f64  # noqa
