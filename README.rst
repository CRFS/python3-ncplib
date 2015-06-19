ncplib
======

`CRFS <http://www.crfs.com/>`_ NCP library for Python 3.


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

In all the following examples, the code is expected to be run from within an `asyncio coroutine <https://docs.python.org/3/library/asyncio-eventloop.html#coroutines>`_.

Connect to a node::

    from ncplib import connect
    client = yield from connect("127.0.0.1", 9999)

Run a simple command::

    swep_params = yield from client.execute("DSPC", "TIME", {"SAMP": 1024, "FCTR": 1200})
    print(swep_params["PDAT"])

Schedule a recurring command on the DSPL loop and receive multiple responses::

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

Close the connection::

    client.close()
    yield from client.wait_closed()


Advanced usage
--------------

The following example show how `asyncio task functions <https://docs.python.org/3/library/asyncio-task.html#task-functions>`_ can be used to provide additional functionality.

Run multiple commands in parallel, and wait for all responses::

    response = client.send("DSPC", {
        "TIME": {},
        "SWEP": {},
    })
    time_params, swep_params = yield from asyncio.gather(
        response.read_field("TIME"),
        response.read_field("SWEP"),
    )


Support and announcements
-------------------------

Downloads and bug tracking can be found at the `main project
website <https://github.com/CRFS/python3-ncplib>`_.

    
Contributors
------------

The following people were involved in the development of this project.

- Dave Hall - `Blog <http://blog.etianen.com/>`_ | `GitHub <http://github.com/etianen>`_
