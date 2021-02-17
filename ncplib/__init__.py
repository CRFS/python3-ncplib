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


from ncplib.client import *  # noqa
from ncplib.connection import *  # noqa
from ncplib.errors import *  # noqa
from ncplib.server import *  # noqa
from ncplib.values import *  # noqa
