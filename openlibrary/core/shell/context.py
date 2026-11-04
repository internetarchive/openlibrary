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

from openlibrary.core.shell._util import _safe
from openlibrary.core.shell.chrome import (
    AnnouncementBanner,
    _extract_announcement_banner,
    _extract_body_attrs,
    _extract_body_classes,
    _extract_donate_script_url,
    _extract_ol_env,
)
from openlibrary.core.shell.head import HeadContext
from openlibrary.core.shell.header import HeaderContext
from openlibrary.core.shell.request import PageMeta, ShellRequest
from openlibrary.core.shell.shelf_labels import build_shelf_button_labels
from openlibrary.core.shell.user import ShellUser, load_shell_user


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
    shelf_button_labels_json: str
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
    def build(cls, *, req: ShellRequest, page: PageMeta, user: ShellUser | None) -> LayoutContext:
        """Assemble layout data from explicit request/page/user inputs; never from request globals. Does no I/O."""
        from openlibrary.core.env import get_ol_env
        from openlibrary.plugins.openlibrary.code import get_supported_languages
        from openlibrary.plugins.openlibrary.status import get_git_revision_short_hash
        from openlibrary.plugins.upstream.utils import json_encode
        from openlibrary.utils.request_context import get_request_lang, req_context

        return cls(
            show_ol_shell=page.show_ol_shell,
            is_debug=bool(req.params.get("debug")),
            is_bot=_safe(lambda: req_context.get().is_bot, False),
            total_time_ms=req.total_time_ms,
            supported_languages=list(get_supported_languages().values()),
            git_rev_hash=_safe(get_git_revision_short_hash, ""),
            lang=_safe(get_request_lang, "en"),
            stats_summary=req.stats_summary,
            stats_details=req.stats_details,
            body_classes=_extract_body_classes(page, req.path, user),
            body_attrs=_extract_body_attrs(page, user),
            donate_script_url=_extract_donate_script_url(req.params),
            flash_messages=list(req.flash_messages),
            ol_env=_extract_ol_env(),
            is_local_dev=get_ol_env().LOCAL_DEV,
            header=HeaderContext.build(req=req, user=user),
            head=HeadContext.build(req=req, page=page, user=user),
            shelf_button_labels_json=json_encode(build_shelf_button_labels()),
            announcement_banner=_extract_announcement_banner(req.banner_dismissed),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to plain dict if needed."""
        return asdict(self)


class SiteLayoutTemplate:
    """``site`` pile entry whose ``filename`` satisfies saferender()'s error path."""

    filename = "openlibrary/templates/shell/base.html.jinja"

    def __call__(self, page: Any) -> str:
        import web

        req, meta = ShellRequest.from_webpy(), PageMeta.from_infogami_ctx(title=getattr(page, "title", "") or "")
        html = render_site(page, req, meta, load_shell_user())
        # Shown now, so consume them: infogami's flash_processor then expires the cookie.
        web.ctx.flash = []
        return html


def render_site(content: Any, req: ShellRequest, page: PageMeta, user: ShellUser | None) -> str:
    """Render ``content`` inside the site shell. Shared by web.py and FastAPI. Does no I/O: load ``user`` first."""
    from openlibrary.core.jinja import render_jinja_template

    return render_jinja_template("shell/base.html.jinja", page=content, layout=LayoutContext.build(req=req, page=page, user=user))
