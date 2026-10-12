"""Site layout context for the Jinja shell.

This module owns the data that drives ``shell/base.html.jinja``. It composes
the per-region contexts (head, header, chrome) and is deliberately separate
from ``openlibrary.core.jinja`` so the Jinja environment (loaders, globals,
filters, i18n) stays easy to reason about in isolation. Templates remain pure:
Python prepares data, Jinja renders it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from openlibrary.accounts import get_current_user
from openlibrary.core.shell._util import _safe
from openlibrary.core.shell.chrome import (
    AnnouncementBanner,
    _extract_announcement_banner,
    _extract_body_attrs,
    _extract_body_classes,
    _extract_donate_script_url,
    _extract_flash_messages,
    _extract_ol_env,
    _extract_stats_details,
    _extract_stats_summary,
    _extract_total_time_ms,
)
from openlibrary.core.shell.head import HeadContext
from openlibrary.core.shell.header import HeaderContext


@dataclass(frozen=True)
class LayoutContext:
    """Precomputed data for the site layout. Strictly data, immutable.

    Convention: no field should hold a callable. This keeps the Jinja
    layout side effect-free and fast — no network or DB calls can hide
    in the template via a passed function. Enforced by tests in
    `openlibrary/tests/core/test_layout.py`.
    """

    show_ol_shell: bool
    is_debug: bool
    is_bot: bool
    total_time_ms: float
    supported_languages: list[dict[str, Any]]
    git_rev_hash: str
    lang: str
    stats_summary: dict[str, Any]
    stats_details: list[Any]
    body_classes: list[str]
    body_attrs: list[str]
    donate_script_url: str
    flash_messages: list[dict[str, str]]
    ol_env: str
    is_local_dev: bool
    header: HeaderContext
    head: HeadContext
    announcement_banner: AnnouncementBanner | None = None

    @property
    def body_class(self) -> str:
        """Backward-compatibility property returning joined body classes."""
        return " ".join(self.body_classes)

    @property
    def active_ui_lang(self) -> dict[str, str]:
        """Resolve active language metadata from request language and supported languages."""
        for lang_info in self.supported_languages:
            if lang_info.get("code") == self.lang:
                return lang_info
        for lang_info in self.supported_languages:
            if lang_info.get("code") == "en":
                return lang_info
        return {"code": "en", "localized": "English", "native": "English"}

    @classmethod
    def build(cls, *, title: str = "") -> LayoutContext:
        """Assemble and compute layout context safely with fallbacks."""
        from infogami.utils.context import context as _infogami_context
        from infogami.utils.view import query_param
        from openlibrary.core.env import get_ol_env
        from openlibrary.plugins.openlibrary.code import get_supported_languages
        from openlibrary.plugins.openlibrary.status import get_git_revision_short_hash
        from openlibrary.utils.request_context import get_request_lang, req_context

        user = _safe(get_current_user, None)

        return cls(
            show_ol_shell=_safe(lambda: _infogami_context.get("show_ol_shell", True), True),
            is_debug=_safe(lambda: bool(query_param("debug")), False),
            is_bot=_safe(lambda: req_context.get().is_bot, False),
            total_time_ms=_safe(_extract_total_time_ms, 0.0),
            supported_languages=list(get_supported_languages().values()),
            git_rev_hash=_safe(get_git_revision_short_hash, ""),
            lang=_safe(get_request_lang, "en"),
            stats_summary=_safe(_extract_stats_summary, {}),
            stats_details=_safe(_extract_stats_details, []),
            body_classes=_extract_body_classes(user),
            body_attrs=_extract_body_attrs(user),
            donate_script_url=_safe(_extract_donate_script_url, "/cdn/archive.org/donate.js"),
            flash_messages=_extract_flash_messages(),
            ol_env=_extract_ol_env(),
            is_local_dev=get_ol_env().LOCAL_DEV,
            header=HeaderContext.build(user=user),
            head=HeadContext.build(title=title, user=user),
            announcement_banner=_extract_announcement_banner(),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to plain dict if needed."""
        return asdict(self)


class SiteLayoutTemplate:
    """``site`` pile entry whose ``filename`` satisfies saferender()'s error path."""

    filename = "openlibrary/templates/shell/base.html.jinja"

    def __call__(self, page: Any) -> str:
        from openlibrary.core.jinja import render_jinja_template

        layout = LayoutContext.build(title=getattr(page, "title", "") or "")
        return render_jinja_template("shell/base.html.jinja", page=page, layout=layout)
