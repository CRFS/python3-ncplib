ncplib
======

NCP library for Python 3, by `CRFS <http://www.crfs.com/>`_


Features
--------

- NCP client library.
- Asynchronous connections via `asyncio <https://docs.python.org/3.4/library/asyncio.html>`_.
- Works in Python 3!


Installation
------------

1. Install using ``pip install ncplib``.


Basic usage
-----------

In the following examples, the code should be run from within an `asyncio coroutine <https://docs.python.org/3/library/asyncio-eventloop.html#coroutines>`_.

Connect to a node:

.. code:: python

    from ncplib import connect
    client = yield from connect("127.0.0.1", 9999)

Run a simple command:

.. code:: python

    swep_params = yield from client.execute("DSPC", "TIME", {"SAMP": 1024, "FCTR": 1200})
    print(swep_params["PDAT"])

Schedule a recurring command on the DSPL loop and receive multiple responses:

.. code:: python

    response = client.send("DSPL", {
        "TIME": {
            "SAMP": 1024,
            "FCTR": 1200,
        }
    })
    time_params_1 = yield from response.recv_field("TIME")
    print(time_params_1["DIQT"])
    time_params_2 = yield from response.recv_field("TIME")
    print(time_params_2["DIQT"])

Close the connection:

.. code:: python

    client.close()
    yield from client.wait_closed()


Advanced usage
--------------

The following example show how `asyncio task functions <https://docs.python.org/3/library/asyncio-task.html#task-functions>`_ can be used to provide additional functionality.

Run multiple commands in parallel, and wait for all responses:

.. code:: python

    response = client.send("DSPC", {
        "TIME": {},
        "SWEP": {},
    })
    time_params, swep_params = yield from asyncio.gather(
        response.read_field("TIME"),
        response.read_field("SWEP"),
    )


Data types
----------

NCP data types are mapped onto python types as follows:

=========== ===========================
NCP type    Python type
----------- ---------------------------
int32       `int`
uint32      `ncplib.uint`
string      `str`
raw         `bytes`
data int8   `arrays.array(typecode="b")`
data int16  `arrays.array(typecode="h")`
data int32  `arrays.array(typecode="i")`
data uint8  `arrays.array(typecode="B")`
data uint16 `arrays.array(typecode="H")`
data uint32 `arrays.array(typecode="I")`


Support and announcements
-------------------------

Downloads and bug tracking can be found at the `main project
website <https://github.com/CRFS/python3-ncplib>`_.

    
Contributors
------------

The following people were involved in the development of this project.

- Dave Hall - `Blog <http://blog.etianen.com/>`_ | `GitHub <http://github.com/etianen>`_
