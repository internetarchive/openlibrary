"""Site layout context for the Jinja shell.

This module owns the data that drives ``site.html.jinja``. It is
deliberately separate from ``openlibrary.core.jinja`` so the Jinja
environment (loaders, globals, filters, i18n) stays easy to reason about
in isolation. Templates remain pure: Python prepares data, Jinja renders it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any, TypeVar

from openlibrary.accounts import get_current_user

if TYPE_CHECKING:
    from openlibrary.core.models import User

T = TypeVar("T")


def _safe[T](fn: Callable[[], T], default: T) -> T:
    """Execute a function and return its result, falling back to default on any failure."""
    try:
        val = fn()
        return default if val is None else val
    except Exception:  # noqa: BLE001
        return default


def _extract_total_time_ms() -> float:
    from infogami.utils import stats as _stats

    val = _stats.stats_summary() or {}
    if not isinstance(val, dict):
        return 0.0
    raw_time = val.get("total", {}).get("time")
    return float(raw_time) * 1000 if raw_time not in (None, "") else 0.0


# TODO: FastAPI does not populate web.ctx.stats, so this returns {}
# under FastAPI (debug table will be empty). Investigate bridging
# infogami stats to ContextVar / middleware so FastAPI requests collect stats.
def _extract_stats_summary() -> dict[str, Any]:
    from infogami.utils import stats as _stats

    val = _stats.stats_summary()
    return val if isinstance(val, dict) else {}


def _extract_stats_details() -> list[Any]:
    from infogami.utils.context import context as _ctx

    try:
        val = _ctx.get("stats", [])
        return val if isinstance(val, list) else []
    except Exception:  # noqa: BLE001
        return []


def can_show_librarian_tools(path: str, user: User) -> bool:
    """Check whether librarian environment tools should be active for the current path and user."""
    if not (path and any(path.startswith(prefix) for prefix in ("/works/OL", "/authors/OL", "/books/OL", "/search"))):
        return False
    if not user:
        return False
    return user.is_librarian_or_higher()


def _extract_body_classes() -> list[str]:
    from infogami.utils.context import context as _ctx

    bodyclass = list(_ctx.get("bodyclass", [])) if isinstance(_ctx.get("bodyclass"), (list, tuple)) else []
    show_ol_shell = _ctx.get("show_ol_shell", True)
    path = getattr(_ctx, "path", "") or _ctx.get("path", "")

    if show_ol_shell and can_show_librarian_tools(path, get_current_user()):
        bodyclass.append("show-librarian-tools")

    return bodyclass


def _extract_body_attrs() -> list[str]:
    """Extract body attributes from the request context."""
    from infogami.utils.context import context as _ctx

    bodyattrs = list(_ctx.get("bodyattrs", [])) if isinstance(_ctx.get("bodyattrs"), (list, tuple)) else []
    # For book-state.js: carousel shelf buttons are rendered without a reader.
    if user := get_current_user():
        bodyattrs.append(f'data-user-key="{user.key}"')
    return bodyattrs


def _extract_donate_script_url() -> str:
    from openlibrary.plugins.upstream.utils import get_ia_host

    ia_host = get_ia_host(allow_dev=True)
    if ia_host != "archive.org":
        return f"https://{ia_host}/includes/donate.js"
    return "/cdn/archive.org/donate.js"


def _extract_flash_messages() -> list[dict[str, str]]:
    try:
        from infogami.utils.flash import get_flash_messages

        messages = get_flash_messages() or []
        result: list[dict[str, str]] = []
        for m in messages:
            if isinstance(m, dict):
                result.append({"type": str(m.get("type", "")), "message": str(m.get("message", ""))})
            elif hasattr(m, "type") and hasattr(m, "message"):
                result.append({"type": str(getattr(m, "type", "")), "message": str(getattr(m, "message", ""))})
        return result
    except Exception:  # noqa: BLE001
        return []


@dataclass(frozen=True)
class AnnouncementBanner:
    """Configuration for a dismissible announcement banner."""

    content: str
    cookie_name: str
    cookie_duration_days: int = 30


def _extract_announcement_banner() -> AnnouncementBanner | None:
    announcement = ""
    cookie_name = ""
    cookie_duration_days = 30
    if not (announcement and cookie_name):
        return None

    try:
        import web

        cookie_val = web.cookies().get(cookie_name)
        if cookie_val == "1":
            return None
    except Exception:  # noqa: BLE001
        pass

    return AnnouncementBanner(
        content=announcement,
        cookie_name=cookie_name,
        cookie_duration_days=cookie_duration_days,
    )


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
    announcement_banner: AnnouncementBanner | None = None

    @property
    def donate_script_src(self) -> str:
        """Backward-compatibility alias for donate_script_url."""
        return self.donate_script_url

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
    def build(cls) -> LayoutContext:
        """Assemble and compute layout context safely with fallbacks."""
        from infogami.utils.context import context as _infogami_context
        from infogami.utils.view import query_param
        from openlibrary.plugins.openlibrary.code import get_supported_languages
        from openlibrary.plugins.openlibrary.status import get_git_revision_short_hash
        from openlibrary.utils.request_context import get_request_lang, req_context

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
            body_classes=_extract_body_classes(),
            body_attrs=_extract_body_attrs(),
            donate_script_url=_safe(_extract_donate_script_url, "/cdn/archive.org/donate.js"),
            flash_messages=_extract_flash_messages(),
            announcement_banner=_safe(_extract_announcement_banner, None),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to plain dict if needed."""
        return asdict(self)


class SiteLayoutTemplate:
    """``site`` pile entry whose ``filename`` satisfies saferender()'s error path."""

    filename = "openlibrary/templates/site.html.jinja"

    def __call__(self, page: Any) -> str:
        from openlibrary.core.jinja import render_jinja_template

        layout = LayoutContext.build()
        return render_jinja_template("site.html.jinja", page=page, layout=layout)
