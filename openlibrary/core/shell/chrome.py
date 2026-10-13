"""Precomputed chrome data for the site shell.

Body classes/attrs, the donate script, flash messages, the announcement
banner and the debug stats table. These feed ``LayoutContext`` directly
(see ``openlibrary/core/shell/context.py``); they are not per-page head or
header data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from openlibrary.core.shell._util import _safe

if TYPE_CHECKING:
    from openlibrary.core.models import User


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


def can_show_librarian_tools(path: str, user: User | None) -> bool:
    """Check whether librarian environment tools should be active for the current path and user."""
    if not (path and any(path.startswith(prefix) for prefix in ("/works/OL", "/authors/OL", "/books/OL", "/search"))):
        return False
    if not user:
        return False
    return user.is_librarian_or_higher()


def _extract_body_classes(user: User | None) -> list[str]:
    from infogami.utils.context import context as _ctx

    bodyclass = list(_ctx.get("bodyclass", [])) if isinstance(_ctx.get("bodyclass"), (list, tuple)) else []
    show_ol_shell = _ctx.get("show_ol_shell", True)
    path = getattr(_ctx, "path", "")

    if show_ol_shell and can_show_librarian_tools(path, user):
        bodyclass.append("show-librarian-tools")

    return bodyclass


def _extract_body_attrs(user: User | None) -> list[str]:
    """Extract body attributes from the request context."""
    from infogami.utils.context import context as _ctx

    bodyattrs = list(_ctx.get("bodyattrs", [])) if isinstance(_ctx.get("bodyattrs"), (list, tuple)) else []
    # For book-state.js: carousel shelf buttons are rendered without a reader.
    if user:
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
    """Banner content is configured here; with no content there is never a banner."""
    announcement = ""
    cookie_name = ""
    cookie_duration_days = 30
    if not announcement or not cookie_name:
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


def _extract_ol_env() -> str:
    from openlibrary.core.env import get_deployment_name

    return _safe(get_deployment_name, "production")
