ncplib
======

NCP library for Python 3, by `CRFS <http://www.crfs.com/>`_


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

In the following examples, the code should be run from within a `coroutine <https://docs.python.org/3/reference/compound_stmts.html#async-def>`_.

Connect to a node:

.. code:: python

    from ncplib import connect
    client = await connect("127.0.0.1", 9999)

Run a simple command:

.. code:: python

    swep_params = await client.execute("DSPC", "TIME", SAMP=1024, FCTR=1200)
    print(swep_params["PDAT"])

Schedule a recurring command on the DSPL loop and receive multiple responses:

.. code:: python

    response = client.send("DSPL", "TIME", SAMP=1024, FCTR=1200)
    async for time_params in response:
        print(time_params["DIQT"])

Close the connection:

.. code:: python

    client.close()
    await client.wait_closed()


Advanced usage
--------------

The following example show how `asyncio task functions <https://docs.python.org/3/library/asyncio-task.html#task-functions>`_ can be used to provide additional functionality.

Run multiple commands in parallel, and wait for all responses:

.. code:: python

    response = client.send("DSPC", {
        "TIME": {},
        "SWEP": {},
    })
    time_params, swep_params = await asyncio.gather(
        response.read_field("TIME"),
        response.read_field("SWEP"),
    )


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
