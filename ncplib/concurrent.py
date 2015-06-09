import asyncio
from functools import wraps


def sync(loop=None):
    loop = loop or asyncio.get_event_loop()
    def decorator(func):
        assert asyncio.iscoroutinefunction(func), "Can only decorate coroutine functions as @sync()."
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            return loop.run_until_complete(func(*args, **kwargs))
        return sync_wrapper
    return decorator


class SyncWrapper:

    __slots__ = ("_wrapped", "_loop",)

    def __init__(self, wrapped, *, loop=None):
        self._wrapped = wrapped
        self._loop = loop or asyncio.get_event_loop()

    def __getattr__(self, name):
        value = getattr(self._wrapped, name)
        if asyncio.iscoroutinefunction(value):
            value = sync(self._loop)(value)
        return value
