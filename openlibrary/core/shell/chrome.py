"""Precomputed chrome data for the site shell.

Body classes/attrs, the donate script, flash messages, the announcement
banner and the debug stats table. These feed ``LayoutContext`` directly
(see ``openlibrary/core/shell/context.py``); they are not per-page head or
header data.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from openlibrary.core.shell._util import _safe

if TYPE_CHECKING:
    from openlibrary.core.models import User
    from openlibrary.core.shell.request import PageMeta


def _extract_total_time_ms() -> float:
    from infogami.utils import stats as _stats

    val = _stats.stats_summary() or {}
    if not isinstance(val, dict):
        return 0.0
    raw_time = val.get("total", {}).get("time")
    return float(raw_time) * 1000 if raw_time not in (None, "") else 0.0


# web.py only (read by ShellRequest.from_webpy): FastAPI never resets
# web.ctx.stats, so reading it there would show other requests' stats.
# See notes/ISSUE-fastapi-debug-stats-leak.md.
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


def _extract_body_classes(page: PageMeta, path: str, user: User | None) -> list[str]:
    bodyclass = list(page.bodyclass)
    if page.show_ol_shell and can_show_librarian_tools(path, user):
        bodyclass.append("show-librarian-tools")
    return bodyclass


def _extract_body_attrs(page: PageMeta, user: User | None) -> list[str]:
    bodyattrs = list(page.bodyattrs)
    # For book-state.js: carousel shelf buttons are rendered without a reader.
    if user:
        bodyattrs.append(f'data-user-key="{user.key}"')
    return bodyattrs


def _extract_donate_script_url(params: dict[str, str]) -> str:
    """Pure twin of ``get_ia_host(allow_dev=True)``: a valid ``?dev_host=`` points at that IA host."""
    dev_host = params.get("dev_host", "")
    if dev_host and re.match("^[a-zA-Z0-9-.]+$", dev_host):
        return f"https://{dev_host}.archive.org/includes/donate.js"
    return "/cdn/archive.org/donate.js"


@dataclass(frozen=True)
class AnnouncementBanner:
    """Configuration for a dismissible announcement banner."""

    content: str
    cookie_name: str
    cookie_duration_days: int = 30


#: Announcement banner config; with no content there is never a banner. A
#: dismissed banner sets ``ANNOUNCEMENT_COOKIE=1`` client-side.
ANNOUNCEMENT = ""
ANNOUNCEMENT_COOKIE = ""
ANNOUNCEMENT_COOKIE_DAYS = 30


def _extract_announcement_banner(banner_dismissed: bool) -> AnnouncementBanner | None:
    if not ANNOUNCEMENT or not ANNOUNCEMENT_COOKIE or banner_dismissed:
        return None
    return AnnouncementBanner(content=ANNOUNCEMENT, cookie_name=ANNOUNCEMENT_COOKIE, cookie_duration_days=ANNOUNCEMENT_COOKIE_DAYS)


def _extract_ol_env() -> str:
    from openlibrary.core.env import get_deployment_name

    return _safe(get_deployment_name, "production")
