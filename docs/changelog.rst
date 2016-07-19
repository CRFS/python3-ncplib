Changelog
=========

.. currentmodule:: ncplib


2.0.1 - 19/07/2016
------------------

- Added :func:`run_app` function to :doc:`server`.


2.0.0 - 17/03/2016
------------------

This release requires a minimum Python version of 3.5. This allows :mod:`ncplib` to take advantage of new native support for coroutines in Python 3.5. It also provides a new :func:`start_server` function for creating a :doc:`server`.

A number of interfaces have been updated or removed in order to take better advantage of Python 3.5 async features, and to unify the interface between :doc:`client` and :doc:`server` connections. Please read the detailed release notes below for more information.

-   :doc:`server` support.
-   :class:`Connection` can be used as an *async context manager*.
-   :meth:`Connection.send` has a cleaner API, allowing params to be specified as keyword arguments.
-   :meth:`Connection.send` and :meth:`Connection.send_packet` return a :class:`Response` that can be used to access replies to the original messages.
-   :meth:`Connection.recv`, :meth:`Connection.recv_field`, :meth:`Response.recv` and :meth:`Response.recv_field` return a :class:`Field` instance, representing a :term:`NCP field`.
-   :class:`Connection` and :class:`Response` can be used as an *async iterator* of :class:`Field`.
-   :meth:`Field.send` allows direct replies to be sent to the incoming :term:`NCP field`.
-   **Breaking:** Python 3.5 is now the minimum supported Python version.
-   **Breaking:** :meth:`Connection.send()` API has changed to be single-field. Use :meth:`Connection.send_packet` to send a multi-field :term:`NCP packet`.
-   **Breaking:** ``Connection.execute()`` has been removed. Use ``Connection.send().recv()`` instead.


1.0.1 - 21/12/2015
------------------

- Automated build and release of package to private Anaconda Cloud channel.


1.0.0 - 07/12/2015
------------------

- First production release.
