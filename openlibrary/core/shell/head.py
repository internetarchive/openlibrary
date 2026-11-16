"""Precomputed data for the site head (``templates/shell/head.html.jinja``).

The head is its own concern and pulls from a distinct set of per-page values,
so it is grouped separately from the rest of ``LayoutContext``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from openlibrary.core.shell._util import _safe

if TYPE_CHECKING:
    from openlibrary.core.shell.request import PageMeta, ShellRequest
    from openlibrary.core.shell.user import ShellUser


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
    def build(cls, *, req: ShellRequest, page: PageMeta, user: ShellUser | None) -> HeadContext:
        from openlibrary.accounts import get_days_registered
        from openlibrary.plugins.upstream.utils import canonical_url, icon_sprite_url, json_encode

        return cls(
            title=page.title,
            domain=req.host,
            # The host comes from the client: a malformed one (``Host: [``) makes urlparse raise.
            canonical_url=_safe(lambda: canonical_url(req.host, req.readable_path, f"?{req.query_string}" if req.query_string else ""), ""),
            disable_analytics=page.disable_analytics,
            page_css_path=f"build/css/page-{page.cssfile}.css",
            experiments_json=_safe(lambda: json_encode(req.experiments), "{}"),
            robots=page.robots,
            description=page.description,
            links=list(page.links),
            metatags=list(page.metatags),
            icon_sprite_url=_safe(icon_sprite_url, "/static/icons/sprite.svg"),
            days_registered_json=_safe(lambda: json_encode(get_days_registered(user)), '"visitor"'),
            sentry=SentryContext.build(),
        )
