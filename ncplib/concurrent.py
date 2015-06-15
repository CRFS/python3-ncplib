import asyncio, inspect
from functools import wraps


def maybe_wrap(value):
    # Wrap coroutine functions.
    if asyncio.iscoroutinefunction(value):
        return sync(value)
    for _, method in inspect.getmembers(value, predicate=inspect.ismethod):
        if asyncio.iscoroutinefunction(method):
            return SyncWrapper(value)
    return value


def sync(func):
    assert asyncio.iscoroutinefunction(func), "Can only decorate coroutine functions as @sync()."
    @wraps(func)
    def sync_wrapper(*args, loop=None, timeout=None, **kwargs):
        loop = loop or asyncio.get_event_loop()
        result = loop.run_until_complete(asyncio.wait_for(func(*args, **kwargs), loop=loop, timeout=timeout))
        return maybe_wrap(result)
    return sync_wrapper


class SyncWrapper:

    __slots__ = ("_wrapped",)

    def __init__(self, wrapped):
        self._wrapped = wrapped

    # Use as a context manager.

    def __enter__(self):
        return maybe_wrap(self._wrapped.__enter__())

    def __exit__(self, *args):
        return maybe_wrap(self._wrapped.__exit__(*args))

    def __getattr__(self, name):
        return maybe_wrap(getattr(self._wrapped, name))
