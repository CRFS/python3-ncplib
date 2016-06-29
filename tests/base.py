import asyncio
import unittest
from functools import wraps


class AsyncTestCase(unittest.TestCase):

    def __init__(self, methodName):
        # Wrap method in coroutine.
        func = getattr(self, methodName)
        if asyncio.iscoroutinefunction(func):
            @wraps(func)
            def do_async_test(*args, **kwargs):
                self.loop.run_until_complete(func(*args, **kwargs))
            setattr(self, methodName, do_async_test)
        # All done!
        super().__init__(methodName)

    # Fixtures.

    def setupFixture(self, fixture):  # pragma: no cover
        self.addCleanup(fixture.__exit__, None, None, None)
        return fixture.__enter__()

    def setupAsyncFixture(self, fixture):  # pragma: no cover
        context = self.loop.run_until_complete(fixture)
        self.addCleanup(self.loop.run_until_complete, context.__aexit__(None, None, None))
        return self.loop.run_until_complete(context.__aenter__())

    def setUp(self):
        super().setUp()
        self.loop = asyncio.new_event_loop()
        self.addCleanup(self.loop.close)
