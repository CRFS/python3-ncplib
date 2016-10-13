"""
ncplib
======

:term:`NCP` library for Python 3, developed by `CRFS`_.

.. image:: https://travis-ci.org/CRFS/python3-ncplib.svg?branch=master
    :target: https://travis-ci.org/CRFS/python3-ncplib


Features
--------

-   :doc:`client`.
-   :doc:`server`.
-   Asynchronous connections via :mod:`asyncio`.


Resources
---------

-   `Documentation`_ is on Read the Docs.
-   `Issue tracking`_ and `source code`_ is on GitHub.
-   `Continuous integration`_ is on Travis CI.


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


__version__ = (2, 0, 8)


from ncplib.client import *  # noqa
from ncplib.connection import *  # noqa
from ncplib.errors import *  # noqa
from ncplib.helpers import *  # noqa
from ncplib.server import *  # noqa
from ncplib.values import *  # noqa
