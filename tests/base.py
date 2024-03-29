from __future__ import annotations
import asyncio
from typing import Any
import unittest
from functools import wraps


class AsyncTestCase(unittest.TestCase):

    loop: asyncio.AbstractEventLoop

    def __init__(self, methodName: str) -> None:
        # Wrap method in coroutine.
        func = getattr(self, methodName)
        if asyncio.iscoroutinefunction(func):
            @wraps(func)
            def do_async_test(*args: Any, **kwargs: Any) -> None:
                self.loop.run_until_complete(asyncio.wait_for(func(*args, **kwargs), 6))
            setattr(self, methodName, do_async_test)
        # All done!
        super().__init__(methodName)

    # Fixtures.

    def setUp(self) -> None:
        super().setUp()
        self.loop = asyncio.new_event_loop()
        self.loop.set_debug(True)
        asyncio.set_event_loop(self.loop)
        self.addCleanup(asyncio.set_event_loop, None)
        self.addCleanup(self.loop.close)
