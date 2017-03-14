import asyncio


@asyncio.coroutine
def wait_for(coro, timeout, *, loop):
    task = loop.create_task(coro)
    try:
        return (yield from asyncio.wait_for(task, timeout, loop=loop))
    finally:
        if not task.done():
            task.cancel()
