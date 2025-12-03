import asyncio
import threading
from collections.abc import Callable, Coroutine
from contextvars import ContextVar
from typing import Any, ParamSpec, TypeVar

import web
from fastapi import Request

from infogami.infobase.client import Site
from infogami.utils.delegate import create_site

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

# ContextVariables
# These are scoped to a specific request
# Defining them here for now to keep things close together

x_forwarded_for: ContextVar[str] = ContextVar("x_forwarded_for")
user_agent: ContextVar[str] = ContextVar("user_agent")
# TODO: Create an async and stateless version of site so we don't have to do this
site: ContextVar[Site] = ContextVar("site")


def set_context_for_sync_request():
    """
    Sets the contextvars for the current request when called from web.py

    create_site is ultimately temporary as we'll need an async version of site
    That version should be usable without instantiating a site
    """
    site.set(create_site())
    user_agent.set(web.ctx.env.get("HTTP_USER_AGENT", ""))
    x_forwarded_for.set(web.ctx.env.get("HTTP_X_FORWARDED_FOR", "ol-internal"))


def set_context_for_async_request(request: Request):
    """
    These are set automatically in the middleware of fastapi
    They are made available to all requests

    BEFORE ADDING:
    Please consider if we could feasibly just pass it down to the function instead
    This is preferable for testable and maintainable code.
    """
    site.set(create_site())
    user_agent.set(request.headers.get("User-Agent", ""))
    x_forwarded_for.set(request.headers.get("X-Forwarded-For", "ol-internal"))
