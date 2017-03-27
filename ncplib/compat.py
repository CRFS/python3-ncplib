import asyncio
import sys


if sys.version_info >= (3, 4, 3):
    wait_for = asyncio.wait_for
else:
    @asyncio.coroutine
    def wait_for(coro, timeout, *, loop=None):
        loop = loop or asyncio.get_event_loop()
        task = loop.create_task(coro)
        try:
            return (yield from asyncio.wait_for(task, timeout, loop=loop))
        finally:
            if not task.done():
                task.cancel()
