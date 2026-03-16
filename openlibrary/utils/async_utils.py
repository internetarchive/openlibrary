import asyncio
import threading
from collections.abc import Callable, Coroutine
from typing import Any, ParamSpec, TypeVar

# Start a persistent event loop in a background thread.
# This avoids creating/destroying a loop on every call to select().
# More importantly, this lets us call async code from sync code.
# This is important to avoid having duplicate code paths while we start
# experimenting with async code.
# In the ideal world we won't need this as we'll be async all the way down.

# You may be wondering why we don't use syncify from asyncer. The reason is that it just doesn't work.
# Also, who needs an extra library when these few lines work for us.
P = ParamSpec("P")
T = TypeVar("T")
# We can't use the 3.14 syntax yet for the paramspec


class AsyncBridge:
    def __init__(self):
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()

    def run[T](self, coro: Coroutine[Any, Any, T]) -> T:
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result()

    def wrap(self, func: Callable[P, Coroutine[Any, Any, T]]) -> Callable[P, T]:
        """Wrap an async function so it can be called from sync code, preserving type hints."""

        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            return self.run(func(*args, **kwargs))

        return wrapper


async_bridge = AsyncBridge()
