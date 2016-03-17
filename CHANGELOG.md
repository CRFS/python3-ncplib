# ncplib changelog

## 2.0.1 - 16/03/2014

- Fixing infinite timeout when disabling auto_ackn in `Client`.
- Not double-closing client sockets in `Server`.


## 2.0.0 - 15/03/2014

This release requires a minimum Python version of 3.5. This allows `ncplib` to take advantage of new native support
for coroutines in Python 3.5. It also provides a new `Server` interface for creating NCP servers.

A number of interfaces have been deprecated in order to take better advantage of Python 3.5 async features, and to
unify the interface between client and server connections. All deprecated interfaces still work as before, but will
raise a `DeprecationWarning` on use. You should migrate your code to take advantage of the new interfaces. Deprecated
interfaces will be removed in ncplib 2.1.0.

- **Breaking:** Python 3.5 is now the minimum supported Python version.
- `Server` allows NCP servers to be easily created.
- `Connection` can be used as an async context manager.
- `Connection.send()` has a cleaner API, allowing params to be specified as keyword arguments.
- `Connection.send()` and `Connection.send_packet()` return a `Response` that can be used to access direct replies to
  the original messages.
- The `recv()`, `recv_field()` methods of `Connection` and `Response` return a `Message`.
- `Connection` and `Response` can be used as an async iterator of `Message`.
- `Message.send()` allows direct replies to be send to the original message.
- **Deprecated:** `ncplib.connect()` is deprecated in favor of `ncplib.Client`.
- **Deprecated:** `Connection.send()` with multiple fields is deprecated in favor of `Connection.send_packet()`.
- **Deprecated:** `Connection.execute()` is deprecated in favor of `Connection.send().recv()`.


## 1.0.1 - 21/12/2015

- Automated build and release of package to private Anaconda Cloud channel.


## 1.0.0 - 07/12/2015

- First production release.
