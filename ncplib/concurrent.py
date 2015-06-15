import asyncio
from functools import wraps


def sync(*, loop=None, timeout=None):
    loop = loop or asyncio.get_event_loop()
    def decorator(func):
        assert asyncio.iscoroutinefunction(func), "Can only decorate coroutine functions as @sync()."
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            return loop.run_until_complete(asyncio.wait_for(func(*args, **kwargs), loop=loop, timeout=timeout))
        return sync_wrapper
    return decorator


class SyncWrapper:

    def __init__(self, wrapped, *, loop=None, timeout=None):
        self._wrapped = wrapped
        self._loop = loop or asyncio.get_event_loop()
        self._timeout = timeout

    def __getattr__(self, name):
        value = getattr(self._wrapped, name)
        if asyncio.iscoroutinefunction(value):
            value = sync(loop=self._loop, timeout=self._timeout)(value)
        return value
