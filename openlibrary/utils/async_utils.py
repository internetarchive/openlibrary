import asyncio
import threading
from collections.abc import Callable, Coroutine
from contextvars import ContextVar
from dataclasses import dataclass
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

################### ContextVariables ###################


@dataclass(frozen=True)
class RequestContextVars:
    """
    These are scoped to a specific request and should be derived directly from the request.
    Use sparingly.
    """

    x_forwarded_for: str | None
    user_agent: str | None


req_context: ContextVar[RequestContextVars] = ContextVar("req_context")

# TODO: Create an async and stateless version of site so we don't have to do this
site: ContextVar[Site] = ContextVar("site")


def set_context_from_legacy_web_py() -> None:
    """
    Extracts context from the global web.ctx (sync) and populates ContextVars.
    """
    site.set(create_site())
    req_context.set(
        RequestContextVars(
            x_forwarded_for=web.ctx.env.get("HTTP_X_FORWARDED_FOR"),
            user_agent=web.ctx.env.get("HTTP_USER_AGENT"),
        )
    )


def set_context_from_fastapi(request: Request) -> None:
    """
    Extracts context from a FastAPI request (async) and populates ContextVars.
    Should be called within the middleware stack.
    """
    # NOTE: Avoid adding new fields here if they can be passed as function arguments instead.
    site.set(create_site())
    req_context.set(
        RequestContextVars(
            x_forwarded_for=request.headers.get("X-Forwarded-For"),
            user_agent=request.headers.get("User-Agent"),
        )
    )
