ncplib
======

NCP library for Python 3, by `CRFS <http://www.crfs.com/>`_

**Note:** All code examples should be run from within a `coroutine <https://docs.python.org/3/reference/compound_stmts.html#async-def>`_.


Features
--------

- NCP client library.
- Asynchronous connections via `asyncio <https://docs.python.org/3/library/asyncio.html>`_.
- Works in Python 3!


Installation
------------

1. Install using ``pip install /path/to/ncplib.tar.gz``.


NCP client usage
----------------

Connect to a NCP server:

.. code:: python

    from ncplib import Client
    async with Client("127.0.0.1", 9999) as client:
        pass  # Your client code here.

Run a simple command:

.. code:: python

    message = await client.execute("DSPC", "TIME", SAMP=1024, FCTR=1200)
    print(message["PDAT"])

Schedule a recurring command on the DSPL loop and receive multiple responses:

.. code:: python

    response = client.send("DSPL", "TIME", SAMP=1024, FCTR=1200)
    async for message in response:
        print(message["DIQT"])

Run multiple commands in parallel, and wait for all responses:

.. code:: python

    response = client.send_packet("DSPC", TIME={}, SWEP={})
    time_message, swep_message = await asyncio.gather(
        response.recv_field("TIME"),
        response.recv_field("SWEP"),
    )


NCP server usage
----------------

Start a server:

.. code:: python

    import asyncio
    from ncplib import Server

    async def echo_server(client):
        for message in client:
            message.send(**message)

    async with Server(echo_server, "127.0.0.1", 9999) as server:
        asyncio.get_event_loop().run_forever()


Library reference
-----------------


``Connection``
~~~~~~~~~~~~~~

Base class for NCP client and server connections.

A ``Connection`` can be used as an async iterator of incoming messages.

.. code:: python

    async for message in Connection:
        print(message)

A ``Connection`` also be used an an async context manager.

.. code:: python

    async with connection:
        pass  # Perform some IO.
    # `connection` is now closed

``async recv()``
    Reads a single ``Message`` from the ``Connection``.

``async recv_field(packet_type, field_name)``
    Reads a single ``Message`` from the ``Connection`` matching the given ``packet_type`` and ``field_name``.

``send(packet_type, field_name, **params)``
    Sends a ``Message`` to the ``Connection``'s peer. The ``Message`` will be sent in an NCP packet containing a single
    field with the given ``field_name`` and ``params``. Returns a ``Response`` for reading replies to the
    ``Message``.

``send_packet(packet_type, **fields)``
    Sends multiple messages to the connection's peer. The messages will be sent in a single NCP packet
    containing all fields. Returns a ``Response`` for reading replies to the messages.

``close()``
    Closes the ``Connection``. Use ``wait_closed()`` to wait for the ``Connection`` to fully close.

``async wait_closed()``
    Waits for the ``Connection`` to fully close.


``Message``
~~~~~~~~~~~

An NCP field and associated parameters received from a `Connection`.

A ``Message`` can be used as a `dict` for reading params from the NCP field.

.. code:: python

    print(message["PDAT"])

``connection``
    The ``Connection`` that received the ``Message``.

``packet_type``
    The packet type of the ``Message`` as a ``str``.

``packet_timestamp``
    The packet timestamp of the ``Message`` as a ``datetime``.

``field_name``
    The name of the field of the ``Message`` as a ``str``.

``field_id``
    The id of the field of the ``Message`` as an ``int``.

``send(**params)``
    Sends a reply to this message containing the given ``params``. The reply will be sent as a single NCP packet
    with metadata that marks it as a reply to the original message.


``Response``
~~~~~~~~~~~~

Represents zero or more replies to a ``Message``.

A ``Response`` can be used as an async iterator of messages that are replies to the original ``Message``..

.. code:: python

    response = connection.send("DSPL", "TIME", SAMP=1024, FCTR=1200)
    async for message in response:
        print(message["DIQT"])

``async recv()``
    Reads a single ``Message`` from the ``Response``.

``async recv_field(field_name)``
    Reads a single ``Message`` from the ``Response`` matching the given ``field_name``. This is only useful for
    responses to a ``sent_packet()`` call containing multiple fields.


Data types
----------

NCP data types are mapped onto python types as follows:

=========== ==================================
NCP type    Python type
=========== ==================================
int32       :code:`int`
uint32      :code:`ncplib.uint`
string      :code:`str`
raw         :code:`bytes`
data int8   :code:`arrays.array(typecode="b")`
data int16  :code:`arrays.array(typecode="h")`
data int32  :code:`arrays.array(typecode="i")`
data uint8  :code:`arrays.array(typecode="B")`
data uint16 :code:`arrays.array(typecode="H")`
data uint32 :code:`arrays.array(typecode="I")`
=========== ==================================


Support and announcements
-------------------------

Downloads and bug tracking can be found at the `main project
website <https://github.com/CRFS/python3-ncplib>`_.


Build status
------------

This project is built on every push using the Travis-CI service.

.. image:: https://travis-ci.com/CRFS/python3-ncplib.svg?token=UzMVyRwHLLx7ryTJmK8k&branch=master
    :target: https://travis-ci.com/CRFS/python3-ncplib


Contributors
------------

The following people were involved in the development of this project.

- Dave Hall - `GitHub <http://github.com/etianen>`_
