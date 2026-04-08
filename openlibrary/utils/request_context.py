"""
Request context management for OpenLibrary.

This module provides utilities for managing request-scoped context variables
and parsing request data for both web.py and FastAPI frameworks.
"""

from contextvars import ContextVar
from dataclasses import dataclass
from urllib.parse import unquote

import web
from fastapi import Request

from infogami import config
from infogami.infobase.client import Site
from infogami.utils.delegate import create_site


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
    sfw: bool = False
    is_bot: bool = False


req_context: ContextVar[RequestContextVars] = ContextVar("req_context")

# TODO: Create an async and stateless version of site so we don't have to do this
site: ContextVar[Site] = ContextVar("site")


def setup_site(request: Request | None = None):
    """
    When called from web.py, web.ctx._parsed_cookies is already set.
    When called from FastAPI, we need to set it.
    create_site() automatically uses the cookie to set the auth token
    """
    s = create_site()
    if request:
        cookie_name = config.get("login_cookie_name", "session")
        if cookie_value := request.cookies.get(cookie_name):
            s._conn.set_auth_token(unquote(cookie_value))

    site.set(s)


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


def _parse_solr_editions_from_web() -> bool:
    """Parse solr_editions from web.py context."""

    def read_query_string():
        return web.input(editions=None).get('editions')

    def read_cookie():
        if "SOLR_EDITIONS" in web.ctx.env.get("HTTP_COOKIE", ""):
            return web.cookies().get('SOLR_EDITIONS')

    if (qs_value := read_query_string()) is not None:
        return qs_value == 'true'

    if (cookie_value := read_cookie()) is not None:
        return cookie_value == 'true'

    return True


def _parse_solr_editions_from_fastapi(request) -> bool:
    """Parse solr_editions preference from query string or cookie."""
    if editions_param := request.query_params.get('editions'):
        return editions_param.lower() == 'true'

    if cookie_value := request.cookies.get('SOLR_EDITIONS'):
        return cookie_value.lower() == 'true'

    return True


def set_context_from_legacy_web_py() -> None:
    """
    Extracts context from the global web.ctx and populates ContextVars.
    """
    solr_editions = _parse_solr_editions_from_web()
    print_disabled = bool(web.cookies().get('pd', False))
    sfw = bool(web.cookies().get('sfw', ''))

    # Compute is_bot once during request setup
    is_bot = _compute_is_bot(
        user_agent=web.ctx.env.get("HTTP_USER_AGENT"),
        hhcl=web.ctx.env.get("HTTP_X_HHCL"),
    )

    setup_site()
    req_context.set(
        RequestContextVars(
            x_forwarded_for=web.ctx.env.get("HTTP_X_FORWARDED_FOR"),
            user_agent=web.ctx.env.get("HTTP_USER_AGENT"),
            lang=web.ctx.lang,
            solr_editions=solr_editions,
            print_disabled=print_disabled,
            sfw=sfw,
            is_bot=is_bot,
        )
    )


def set_context_from_fastapi(request: Request) -> None:
    """
    Extracts context from a FastAPI request (async) and populates ContextVars.
    Should be called within the middleware stack.
    """
    # NOTE: Avoid adding new fields here if they can be passed as function arguments instead.

    solr_editions = _parse_solr_editions_from_fastapi(request)

    # Compute is_bot once during request setup
    is_bot = _compute_is_bot(
        user_agent=request.headers.get("User-Agent"),
        hhcl=request.headers.get("X-HHCL"),
    )

    setup_site(request)
    req_context.set(
        RequestContextVars(
            x_forwarded_for=request.headers.get("X-Forwarded-For"),
            user_agent=request.headers.get("User-Agent"),
            lang=request.state.lang,
            solr_editions=solr_editions,
            print_disabled=bool(request.cookies.get('pd', False)),
            sfw=bool(request.cookies.get('sfw', '')),
            is_bot=is_bot,
        )
    )
