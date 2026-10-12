"""Precomputed data for the site head (``templates/shell/head.html.jinja``).

The head is its own concern and pulls from a distinct set of per-page values,
so it is grouped separately from the rest of ``LayoutContext``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from openlibrary.core.shell._util import _safe

if TYPE_CHECKING:
    from openlibrary.core.models import User


@dataclass(frozen=True)
class SentryContext:
    """Precomputed Sentry values for the site head, if Sentry is enabled."""

    traceparent: str
    baggage: str
    frontend_config_json: str

    @classmethod
    def build(cls) -> SentryContext | None:
        from openlibrary.plugins.upstream.utils import json_encode
        from openlibrary.utils.sentry import get_sentry

        sentry = _safe(get_sentry, None)
        if not sentry or not _safe(lambda: bool(sentry.enabled), False):
            return None
        return cls(
            traceparent=_safe(lambda: sentry.get_traceparent() or "", ""),
            baggage=_safe(lambda: sentry.get_baggage() or "", ""),
            frontend_config_json=_safe(lambda: json_encode(sentry.get_frontend_config()), "{}"),
        )


@dataclass(frozen=True)
class HeadContext:
    """Precomputed data for the site head (``shell/head.html.jinja``)."""

    title: str
    domain: str
    canonical_url: str
    disable_analytics: bool
    page_css_path: str
    experiments_json: str
    robots: str
    description: str
    links: list[str]
    metatags: list[str]
    icon_sprite_url: str
    days_registered_json: str
    sentry: SentryContext | None

    @classmethod
    def build(cls, *, title: str, user: User | None) -> HeadContext:
        """Read the per-page infogami ctx and assemble head data with safe fallbacks."""
        from infogami.utils.context import context as _ctx
        from openlibrary.accounts import get_days_registered
        from openlibrary.plugins.upstream.utils import Request, icon_sprite_url, json_encode

        def ctx(key: str, default: Any) -> Any:
            return _safe(lambda: _ctx.get(key, default), default)

        def ctx_str_list(key: str) -> list[str]:
            raw = ctx(key, [])
            return [str(x) for x in raw] if isinstance(raw, (list, tuple)) else []

        request = Request()
        cssfile = ctx("cssfile", "user") or "user"

        return cls(
            title=title,
            domain=_safe(lambda: request.domain or "", ""),
            canonical_url=_safe(lambda: request.canonical_url or "", ""),
            disable_analytics=bool(ctx("disable_analytics", False)),
            page_css_path=f"build/css/page-{cssfile}.css",
            experiments_json=_safe(lambda: json_encode(ctx("experiments", {}) or {}), "{}"),
            robots=str(ctx("robots", "") or ""),
            description=str(ctx("description", "") or ""),
            links=ctx_str_list("links"),
            metatags=ctx_str_list("metatags"),
            icon_sprite_url=_safe(icon_sprite_url, "/static/icons/sprite.svg"),
            days_registered_json=_safe(lambda: json_encode(get_days_registered(user)), '"visitor"'),
            sentry=SentryContext.build(),
        )
