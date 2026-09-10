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
            supported_languages=_safe(lambda: list(get_supported_languages().values()), []),
            git_rev_hash=_safe(get_git_revision_short_hash, ""),
            lang=_safe(get_request_lang, "en"),
            stats_summary=_safe(_extract_stats_summary, {}),
            stats_details=_safe(_extract_stats_details, []),
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
