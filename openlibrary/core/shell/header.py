"""Precomputed data for the site header (``templates/shell/header.html.jinja``).

The header is its own concern and pulls from its own set of per-request
values. ``ol_env``/``is_local_dev`` stay on ``LayoutContext`` because the head
consumes them too.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from openlibrary.core.helpers import datestr
from openlibrary.core.shell._util import _safe
from openlibrary.core.shell.nav import BROWSE_FEATURED_COUNT, NavLink, browse_links
from openlibrary.core.shell.search_modal import SearchModalContext, build_search_modal_i18n
from openlibrary.utils.request_context import get_request_lang

if TYPE_CHECKING:
    from openlibrary.core.shell.request import ShellRequest
    from openlibrary.core.shell.user import ShellUser


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


def _extract_header_user(user: ShellUser | None) -> HeaderUser | None:
    if not user:
        return None

    username = user.key.rsplit("/", maxsplit=1)[-1]
    # Pass lang: datestr() otherwise reads web.ctx.lang, which FastAPI never sets.
    joined_date = _safe(lambda: datestr(created, lang=get_request_lang()), "") if (created := user.created) else ""
    from openlibrary.i18n import gettext as _

    account_title = f"{username}\n{_('Joined %(date)s', date=joined_date)}" if joined_date else username

    return HeaderUser(
        key=user.key,
        username=username,
        ia_id=user.ia_id,
        account_title=account_title,
        is_privileged_user=user.is_librarian,
        shows_merge_count=user.is_super_librarian,
        open_merges_count=user.open_merges_count,
    )


def _extract_my_books_props(homepath: str) -> dict[str, Any]:
    from openlibrary.i18n import gettext as _

    return {
        "name": "mybooks",
        "label": _("My Books"),
        "icon": "bookmark",
        "links": [
            {
                "href": f"{homepath}/account/books",
                "text": _("My Books"),
                "track": "MyBooks",
            }
        ],
        "link-class": "ol-button-static ol-button-static--ghost",
    }


@dataclass(frozen=True)
class HeaderContext:
    """Precomputed data for the site header (``templates/shell/header.html.jinja``)."""

    user: HeaderUser | None
    page_status_url: str
    is_recognized_bot: bool
    is_print_disabled: bool
    homepath: str
    my_books_props: dict[str, Any]
    browse_links: list[NavLink]
    browse_featured_count: int
    search_modal: SearchModalContext

    @classmethod
    def build(cls, *, req: ShellRequest, user: ShellUser | None) -> HeaderContext:
        """Assemble header data with safe fallbacks."""
        from openlibrary.utils.request_context import req_context

        links: list[NavLink] = _safe(browse_links, [])

        return cls(
            user=_extract_header_user(user),
            page_status_url=f"{req.path}?show_page_status=1",
            is_recognized_bot=_safe(lambda: req_context.get().is_recognized_bot, False),
            is_print_disabled=_safe(lambda: req_context.get().print_disabled, False),
            homepath=req.homepath,
            my_books_props=_extract_my_books_props(req.homepath),
            browse_links=links,
            browse_featured_count=BROWSE_FEATURED_COUNT,
            search_modal=build_search_modal_i18n(),
        )
