import asyncio, inspect
from functools import wraps


def maybe_wrap(value, *, loop=None, timeout=None):
    # Wrap coroutine functions.
    if callable(value):
        return sync(value, loop=loop, timeout=timeout)
    if any(inspect.getmembers(value, predicate=asyncio.iscoroutinefunction)):
        return SyncWrapper(value, loop=loop, timeout=timeout)
    return value


def sync(func, *, loop=None, timeout=None):
    signature = inspect.signature(func)
    # Wrap functions with a sync wrapper.
    @wraps(func)
    def sync_wrapper(*args, loop=loop, timeout=timeout, **kwargs):
        # Pass through loop and timeout arguments, if present.
        if "loop" in signature.parameters:
            kwargs["loop"] = loop
        if "timeout" in signature.parameters:
            kwargs["timeout"] = timeout
            timeout = None
        # Run the func.
        result = func(*args, **kwargs)
        # Run coroutines on the loop.
        if asyncio.iscoroutine(result):
            loop = loop or asyncio.get_event_loop()
            # Apply timeout.
            if timeout is not None:
                result = asyncio.wait_for(result, loop=loop, timeout=timeout)
            # Wait for the result to be ready.
            result = loop.run_until_complete(result)
        # Wrap the result.
        return maybe_wrap(result, loop=loop, timeout=timeout)
    return sync_wrapper


class SyncWrapper:

    def __init__(self, wrapped, *, loop=None, timeout=None):
        self._wrapped = wrapped
        self._loop = loop
        self._timeout = timeout

    def __getattr__(self, name):
        return maybe_wrap(getattr(self._wrapped, name), loop=self._loop, timeout=self._timeout)
