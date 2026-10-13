"""Precomputed data for the site header (``templates/shell/header.html.jinja``).

The header is its own concern and pulls from its own set of per-request
values. ``ol_env``/``is_local_dev`` stay on ``LayoutContext`` because the head
consumes them too.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from openlibrary.accounts.model import get_internet_archive_id
from openlibrary.core.edits import cached_get_counts_by_mode
from openlibrary.core.helpers import datestr
from openlibrary.core.shell._util import _safe
from openlibrary.core.shell.nav import BROWSE_FEATURED_COUNT, NavLink, browse_links, mybooks_links
from openlibrary.core.shell.search_modal import SearchModalContext, build_search_modal_i18n

if TYPE_CHECKING:
    from openlibrary.core.models import User


@dataclass(frozen=True)
class HeaderUser:
    """Precomputed user and role information for the site header."""

    key: str
    username: str
    ia_id: str | None
    account_title: str
    is_privileged_user: bool
    shows_merge_count: bool
    open_merges_count: int


def _extract_header_user(user: User | None) -> HeaderUser | None:
    if not user:
        return None

    key = str(getattr(user, "key", "") or "")
    if not key:
        return None
    username = key.rsplit("/", maxsplit=1)[-1]
    ia_id = _safe(lambda: get_internet_archive_id(key), None)
    created = getattr(user, "created", None)
    joined_date = _safe(lambda: datestr(created), "") if created else ""
    from openlibrary.i18n import gettext as _

    account_title = f"{username}\n{_('Joined %(date)s', date=joined_date)}" if joined_date else username
    is_privileged = _safe(lambda: bool(user.is_librarian_or_higher()), False)
    shows_merges = _safe(lambda: bool(user.is_super_librarian_or_higher()), False)
    merge_count = 0
    if shows_merges:
        merge_count = _safe(lambda: int(cached_get_counts_by_mode(mode="open") or 0), 0)

    return HeaderUser(
        key=key,
        username=username,
        ia_id=ia_id,
        account_title=account_title,
        is_privileged_user=is_privileged,
        shows_merge_count=shows_merges,
        open_merges_count=merge_count,
    )


def _extract_page_status_url() -> str:
    try:
        import web

        return web.changequery({"show_page_status": 1})
    except Exception:  # noqa: BLE001
        return "?show_page_status=1"


def _extract_homepath() -> str:
    try:
        import web

        return getattr(web.ctx, "homepath", "") or ""
    except Exception:  # noqa: BLE001
        return ""


@dataclass(frozen=True)
class HeaderContext:
    """Precomputed data for the site header (``templates/shell/header.html.jinja``)."""

    user: HeaderUser | None
    page_status_url: str
    is_recognized_bot: bool
    is_print_disabled: bool
    homepath: str
    mybooks_links: list[list[NavLink]]
    browse_links: list[NavLink]
    browse_featured_count: int
    search_modal: SearchModalContext

    @classmethod
    def build(cls, *, user: User | None) -> HeaderContext:
        """Assemble header data with safe fallbacks."""
        from openlibrary.utils.request_context import req_context

        homepath = _extract_homepath()
        links: list[NavLink] = _safe(browse_links, [])

        return cls(
            user=_extract_header_user(user),
            page_status_url=_extract_page_status_url(),
            is_recognized_bot=_safe(lambda: req_context.get().is_recognized_bot, False),
            is_print_disabled=_safe(lambda: req_context.get().print_disabled, False),
            homepath=homepath,
            mybooks_links=_safe(mybooks_links, [[]]),
            browse_links=links,
            browse_featured_count=BROWSE_FEATURED_COUNT,
            search_modal=build_search_modal_i18n(),
        )
