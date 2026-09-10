"""Site layout context for the Jinja shell.

This module owns the data that drives ``site.html.jinja``. It is
deliberately separate from ``openlibrary.core.jinja`` so the Jinja
environment (loaders, globals, filters, i18n) stays easy to reason about
in isolation. Templates remain pure: Python prepares data, Jinja renders it.
"""

from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any, TypeVar

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


def _extract_body_class_and_attrs() -> tuple[str, str]:
    from infogami.utils.context import context as _ctx

    bodyclass = list(_ctx.get("bodyclass", [])) if isinstance(_ctx.get("bodyclass"), (list, tuple)) else []
    bodyattrs = list(_ctx.get("bodyattrs", [])) if isinstance(_ctx.get("bodyattrs"), (list, tuple)) else []
    show_ol_shell = _ctx.get("show_ol_shell", True)
    path = getattr(_ctx, "path", "") or _ctx.get("path", "")
    user = getattr(_ctx, "user", None) or _ctx.get("user")

    if show_ol_shell and path and any(path.startswith(prefix) for prefix in ("/works/OL", "/authors/OL", "/books/OL", "/search")):
        is_librarian = False
        if user:
            if hasattr(user, "is_librarian_or_higher"):
                is_librarian = user.is_librarian_or_higher()
            elif hasattr(user, "is_librarian") and hasattr(user, "is_admin"):
                is_librarian = user.is_librarian() or user.is_admin()
        if is_librarian:
            bodyclass.append("show-librarian-tools")
            key = getattr(user, "key", "") or (user.get("key", "") if isinstance(user, dict) else "")
            if key:
                username = key.split("/")[-1]
                bodyattrs.append(f'data-username="{username}"')

    return " ".join(bodyclass), " ".join(bodyattrs)


def _extract_active_ui_lang(lang: str, supported: dict[str, dict[str, str]]) -> dict[str, str]:
    if active := supported.get(lang) or supported.get("en"):
        return dict(active)
    return {"code": "en", "localized": "English", "native": "English"}


def _extract_donate_script_src() -> str:
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


def _extract_announcement_banner() -> tuple[bool, str, str, int]:
    announcement = ""
    cookie_name = ""
    cookie_duration_days = 30
    if not (announcement and cookie_name):
        return False, "", "", cookie_duration_days

    try:
        import web

        cookie_val = web.cookies().get(cookie_name)
        show_banner = cookie_val != "1"
    except Exception:  # noqa: BLE001
        show_banner = True

    return show_banner, announcement, cookie_name, cookie_duration_days


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
    body_class: str
    body_attrs: str
    active_ui_lang: dict[str, str]
    donate_script_src: str
    flash_messages: list[dict[str, str]]
    show_announcement_banner: bool
    announcement: str
    announcement_cookie_name: str
    announcement_cookie_duration_days: int

    @classmethod
    def build(cls) -> LayoutContext:
        """Assemble and compute layout context safely with fallbacks."""
        from infogami.utils.context import context as _infogami_context
        from infogami.utils.view import query_param
        from openlibrary.plugins.openlibrary.code import get_supported_languages
        from openlibrary.plugins.openlibrary.status import get_git_revision_short_hash
        from openlibrary.utils.request_context import get_request_lang, req_context

        body_class, body_attrs = _safe(_extract_body_class_and_attrs, ("", ""))
        empty_supported_langs: dict[str, dict[str, str]] = {}
        supported_langs_dict: dict[str, dict[str, str]] = _safe(get_supported_languages, empty_supported_langs)
        lang = _safe(get_request_lang, "en")
        active_ui_lang = _safe(
            lambda: _extract_active_ui_lang(lang, supported_langs_dict),
            {"code": "en", "localized": "English", "native": "English"},
        )
        donate_script_src = _safe(_extract_donate_script_src, "/cdn/archive.org/donate.js")
        empty_flash_messages: list[dict[str, str]] = []
        flash_messages: list[dict[str, str]] = _safe(_extract_flash_messages, empty_flash_messages)
        show_banner, announcement, cookie_name, cookie_duration_days = _safe(_extract_announcement_banner, (False, "", "", 30))

        return cls(
            show_ol_shell=_safe(lambda: _infogami_context.get("show_ol_shell", True), True),
            is_debug=_safe(lambda: bool(query_param("debug")), False),
            is_bot=_safe(lambda: req_context.get().is_bot, False),
            total_time_ms=_safe(_extract_total_time_ms, 0.0),
            supported_languages=list(supported_langs_dict.values()),
            git_rev_hash=_safe(get_git_revision_short_hash, ""),
            lang=lang,
            stats_summary=_safe(_extract_stats_summary, {}),
            stats_details=_safe(_extract_stats_details, []),
            body_class=body_class,
            body_attrs=body_attrs,
            active_ui_lang=active_ui_lang,
            donate_script_src=donate_script_src,
            flash_messages=flash_messages,
            show_announcement_banner=show_banner,
            announcement=announcement,
            announcement_cookie_name=cookie_name,
            announcement_cookie_duration_days=cookie_duration_days,
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
