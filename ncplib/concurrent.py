import asyncio
from functools import wraps


def sync():
    def decorator(func):
        assert asyncio.iscoroutinefunction(func), "Can only decorate coroutine functions as @sync()."
        @wraps(func)
        def sync_wrapper(*args, loop=None, timeout=None, **kwargs):
            loop = loop or asyncio.get_event_loop()
            return loop.run_until_complete(asyncio.wait_for(func(*args, **kwargs), loop=loop, timeout=timeout))
        return sync_wrapper
    return decorator


class SyncWrapper:

    __slots__ = ("_wrapped",)

    def __init__(self, wrapped):
        self._wrapped = wrapped

    def __getattr__(self, name):
        value = getattr(self._wrapped, name)
        if asyncio.iscoroutinefunction(value):
            value = sync()(value)
        return value
