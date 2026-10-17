"""Per-request input for the site shell, built once from web.py or Starlette.

The shell never reads request state from globals. ``web.ctx`` and infogami's
``context`` are thread-locals that FastAPI never resets: async handlers share
one on the event loop thread, and sync handlers inherit whatever the last
request on that worker thread left. A stray read there can put one request's
path, flash message or cookie into another's page. So each server converts its
request into these frozen values up front, and the shell builders read only
them.
"""

from __future__ import annotations

import json
import urllib.parse
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

    from starlette.requests import Request

FLASH_COOKIE = "flash"


@dataclass(frozen=True)
class PageMeta:
    """What a page tells the shell about itself (web.py pages set these via ``$putctx``/``$var``)."""

    title: str = ""
    cssfile: str = "user"
    bodyclass: tuple[str, ...] = ()
    bodyattrs: tuple[str, ...] = ()
    links: tuple[str, ...] = ()
    metatags: tuple[str, ...] = ()
    robots: str = ""
    description: str = ""
    show_ol_shell: bool = True
    disable_analytics: bool = False

    @classmethod
    def from_infogami_ctx(cls, *, title: str) -> PageMeta:
        from infogami.utils.context import context

        def str_tuple(key: str) -> tuple[str, ...]:
            raw = context.get(key)
            return tuple(str(x) for x in raw) if isinstance(raw, (list, tuple)) else ()

        return cls(
            title=title,
            cssfile=context.get("cssfile") or "user",
            bodyclass=str_tuple("bodyclass"),
            bodyattrs=str_tuple("bodyattrs"),
            links=str_tuple("links"),
            metatags=str_tuple("metatags"),
            robots=str(context.get("robots") or ""),
            description=str(context.get("description") or ""),
            show_ol_shell=context.get("show_ol_shell", True),
            disable_analytics=bool(context.get("disable_analytics", False)),
        )


@dataclass(frozen=True)
class ShellRequest:
    """Everything the shell needs from the HTTP request, as plain values.

    Holds no cookies, only what the shell derives from them (flash messages,
    banner dismissal), so the session cookie can never reach a template.
    """

    path: str
    readable_path: str
    query_string: str  # without the leading "?"
    host: str
    homepath: str = ""
    banner_dismissed: bool = False
    flash_messages: tuple[dict[str, str], ...] = ()
    experiments: dict[str, Any] = field(default_factory=dict)
    # Collected by infogami on web.py only; see notes/ISSUE-fastapi-debug-stats-leak.md.
    stats_summary: dict[str, Any] = field(default_factory=dict)
    stats_details: list[Any] = field(default_factory=list)
    total_time_ms: float = 0.0

    @property
    def params(self) -> dict[str, str]:
        """GET params; a repeated key keeps its last value, like ``web.input``."""
        return {k: v[-1] for k, v in urllib.parse.parse_qs(self.query_string, keep_blank_values=True).items()}

    def changequery(self, _path: str | None = None, **kw: Any) -> str:
        """Pure twin of the ``changequery`` Templetor global (``plugins/openlibrary/code.py``)."""
        query: dict[str, Any] = self.params
        for k, v in kw.items():
            if v is None:
                query.pop(k, None)
            else:
                query[k] = v
        out = _path or self.readable_path
        return out + "?" + urllib.parse.urlencode(query, doseq=True) if query else out

    @classmethod
    def from_webpy(cls) -> ShellRequest:
        """Read the current web.py request. Only valid inside web.py's request cycle."""
        import web

        from infogami.utils.context import context
        from openlibrary.core.shell.chrome import _extract_stats_details, _extract_stats_summary, _extract_total_time_ms

        return cls(
            path=web.ctx.path,
            readable_path=web.ctx.get("readable_path", web.ctx.path) or "",
            query_string=(web.ctx.get("query") or "").removeprefix("?"),
            host=web.ctx.host or "",
            homepath=web.ctx.get("homepath", "") or "",
            banner_dismissed=_banner_dismissed(web.cookies()),
            # Read without consuming; SiteLayoutTemplate consumes once the shell is rendered.
            flash_messages=_flash_dicts(web.ctx.get("flash") or []),
            experiments=context.get("experiments") or {},
            stats_summary=_extract_stats_summary(),
            stats_details=_extract_stats_details(),
            total_time_ms=_extract_total_time_ms(),
        )

    @classmethod
    def from_starlette(cls, request: Request) -> ShellRequest:
        """Read a FastAPI request. Stats stay empty: FastAPI doesn't collect infogami stats."""
        try:
            # Starlette doesn't %-decode cookie values; web.py (which sets this cookie) does.
            flash = json.loads(urllib.parse.unquote(request.cookies.get(FLASH_COOKIE, "[]")))
        except ValueError, RecursionError:  # RecursionError: deeply nested JSON from a forged cookie
            flash = []
        return cls(
            path=request.url.path,
            readable_path=request.url.path,
            query_string=request.url.query,
            host=request.headers.get("host", ""),
            homepath=request.scope.get("root_path", ""),
            banner_dismissed=_banner_dismissed(request.cookies),
            flash_messages=_flash_dicts(flash if isinstance(flash, list) else []),
            experiments=getattr(request.state, "experiments", None) or {},
        )


def _banner_dismissed(cookies: Mapping[str, str]) -> bool:
    from openlibrary.core.shell.chrome import ANNOUNCEMENT_COOKIE

    return bool(ANNOUNCEMENT_COOKIE) and cookies.get(ANNOUNCEMENT_COOKIE) == "1"


def _flash_dicts(messages: list[Any]) -> tuple[dict[str, str], ...]:
    """Mirror infogami's ``flash_processor``: keep only well-formed ``{type, message}`` entries."""
    return tuple({"type": str(m["type"]), "message": str(m["message"])} for m in messages if isinstance(m, dict) and "type" in m and "message" in m)
