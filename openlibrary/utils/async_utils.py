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
    lang: str | None
    solr_editions: bool | None
    print_disabled: bool
    is_bot: bool = False


req_context: ContextVar[RequestContextVars] = ContextVar("req_context")

# TODO: Create an async and stateless version of site so we don't have to do this
site: ContextVar[Site] = ContextVar("site")


def _compute_is_bot(user_agent: str | None, hhcl: str | None) -> bool:
    """Determine if the request is from a bot.

    Args:
        user_agent: The User-Agent header value
        hhcl: The X-HHCL header value (set by nginx)

    Returns:
        True if the request appears to be from a bot, False otherwise
    """
    user_agent_bots = [
        'sputnikbot',
        'dotbot',
        'semrushbot',
        'googlebot',
        'yandexbot',
        'monsidobot',
        'kazbtbot',
        'seznambot',
        'dubbotbot',
        '360spider',
        'redditbot',
        'yandexmobilebot',
        'linkdexbot',
        'musobot',
        'mojeekbot',
        'focuseekbot',
        'behloolbot',
        'startmebot',
        'yandexaccessibilitybot',
        'uptimerobot',
        'femtosearchbot',
        'pinterestbot',
        'toutiaospider',
        'yoozbot',
        'parsijoobot',
        'equellaurlbot',
        'donkeybot',
        'paperlibot',
        'nsrbot',
        'discordbot',
        'ahrefsbot',
        'coccocbot',
        'buzzbot',
        'laserlikebot',
        'baiduspider',
        'bingbot',
        'mj12bot',
        'yoozbotadsbot',
        'ahrefsbot',
        'amazonbot',
        'applebot',
        'bingbot',
        'brightbot',
        'gptbot',
        'petalbot',
        'semanticscholarbot',
        'yandex.com/bots',
        'icc-crawler',
    ]

    # Check hhcl header first (set by nginx)
    if hhcl == '1':
        return True

    # Check user agent
    if not user_agent:
        return True

    user_agent = user_agent.lower()
    return any(bot in user_agent for bot in user_agent_bots)


def set_context_from_legacy_web_py() -> None:
    """
    Extracts context from the global web.ctx and populates ContextVars.
    """
    # Avoid circular import
    from openlibrary.plugins.worksearch.schemes.works import (
        _parse_solr_editions_from_web,
    )

    solr_editions = _parse_solr_editions_from_web()
    print_disabled = bool(web.cookies().get('pd', False))

    # Compute is_bot once during request setup
    is_bot = _compute_is_bot(
        user_agent=web.ctx.env.get("HTTP_USER_AGENT"),
        hhcl=web.ctx.env.get("HTTP_X_HHCL"),
    )

    site.set(create_site())
    req_context.set(
        RequestContextVars(
            x_forwarded_for=web.ctx.env.get("HTTP_X_FORWARDED_FOR"),
            user_agent=web.ctx.env.get("HTTP_USER_AGENT"),
            lang=web.ctx.lang,
            solr_editions=solr_editions,
            print_disabled=print_disabled,
            is_bot=is_bot,
        )
    )


def set_context_from_fastapi(request: Request) -> None:
    """
    Extracts context from a FastAPI request (async) and populates ContextVars.
    Should be called within the middleware stack.
    """
    # NOTE: Avoid adding new fields here if they can be passed as function arguments instead.

    # Import here to avoid circular import
    from openlibrary.plugins.worksearch.schemes.works import (
        _parse_solr_editions_from_fastapi,
    )

    solr_editions = _parse_solr_editions_from_fastapi(request)

    # Compute is_bot once during request setup
    is_bot = _compute_is_bot(
        user_agent=request.headers.get("User-Agent"),
        hhcl=request.headers.get("X-HHCL"),
    )

    site.set(create_site())
    req_context.set(
        RequestContextVars(
            x_forwarded_for=request.headers.get("X-Forwarded-For"),
            user_agent=request.headers.get("User-Agent"),
            lang=request.state.lang,
            solr_editions=solr_editions,
            print_disabled=bool(request.cookies.get('pd', False)),
            is_bot=is_bot,
        )
    )
