import asyncio
import contextvars
import functools
import threading
import weakref
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
        ctx = contextvars.copy_context()

        async def _in_ctx() -> T:
            return await asyncio.get_running_loop().create_task(coro, context=ctx)

        return asyncio.run_coroutine_threadsafe(_in_ctx(), self._loop).result()

    def wrap(
        self,
        func: Callable[P, Coroutine[Any, Any, T]],
        name: str | None = None,
    ) -> Callable[P, T]:
        """Wrap an async function so it can be called from sync code, preserving type hints.

        Args:
            func: The async function to wrap
            name: Optional custom name for the wrapper. Defaults to func.__name__.
                  Use this when registering with @public to ensure correct template globals.
        """

        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            return self.run(func(*args, **kwargs))

        wrapper.__name__ = name if name is not None else func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper


async_bridge = AsyncBridge()


def cache_per_event_loop[T](factory: Callable[[], T]) -> Callable[[], T]:
    """Cache a zero-arg factory's result once per running event loop.

    Some resources (notably `httpx.AsyncClient`) lazily bind internal
    `asyncio.Lock`/`asyncio.Event` primitives to whichever event loop is
    running the first time a pooled connection is genuinely contended for,
    and can't be safely reused from a different loop afterwards. `AsyncBridge`
    above runs a persistent event loop on its own thread, separate from
    whatever loop the caller is on (e.g. FastAPI's), so a single process-wide
    client eventually raises `RuntimeError: ... is bound to a different event
    loop` once a connection created on one loop gets reused on the other.

    Caching per-loop preserves connection pooling/keep-alive/DNS-caching
    *within* a loop while keeping different loops fully isolated.
    `WeakKeyDictionary` lets cached values for short-lived loops (e.g. a
    `pytest-asyncio` per-test loop) get garbage collected instead of piling
    up for the life of the process.

    Each call to this function returns an independent cache, same as
    `functools.lru_cache` -- wrapping the same factory twice gives you two
    unrelated per-loop registries, not a shared one.
    """
    cached: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, T] = weakref.WeakKeyDictionary()

    @functools.wraps(factory)
    def get() -> T:
        loop = asyncio.get_running_loop()
        value = cached.get(loop)
        if value is None:
            value = factory()
            cached[loop] = value
        return value

    return get
