"""The logged-in user as the site shell sees it.

Everything the shell needs about the user is looked up here, once per request,
so building and rendering the shell does no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from openlibrary.accounts import get_current_user
from openlibrary.accounts.model import get_internet_archive_id
from openlibrary.core.edits import cached_get_counts_by_mode
from openlibrary.core.shell._util import _safe

if TYPE_CHECKING:
    from datetime import datetime


@dataclass(frozen=True)
class ShellUser:
    """What the shell shows about the logged-in user."""

    key: str
    created: datetime | None
    ia_id: str | None
    is_librarian: bool  # librarian, super-librarian or admin
    is_super_librarian: bool  # super-librarian or admin
    open_merges_count: int  # only looked up for super-librarians, who see it in the header


def load_shell_user() -> ShellUser | None:
    """The user logged in to ``site.get()``, or None for a visitor.

    web.py calls this while rendering. On FastAPI, pages reach it through
    ``get_shell_user`` (``CurrentUserDep``) in ``openlibrary/fastapi/shared/site_page.py``,
    in a worker thread.
    """
    # TODO: Make this async so FastAPI pages need no worker thread. It blocks on infobase
    # (the session's user, the usergroup lookups, the account store) and memcache. The
    # usergroup lookups can use openlibrary.core.infobase_async.things() today; the user
    # and the account store need async readers there, plus checking the session cookie
    # locally. Then SitePageRoute awaits it and web.py calls it through async_bridge.run.
    user = _safe(get_current_user, None)
    if not user or not (key := str(getattr(user, "key", "") or "")):
        return None
    is_super_librarian = _safe(lambda: bool(user.is_super_librarian_or_higher()), False)
    return ShellUser(
        key=key,
        created=getattr(user, "created", None),
        ia_id=_safe(lambda: get_internet_archive_id(key), None),
        # Also records the librarian flag for the request metrics (User.is_librarian_or_higher).
        is_librarian=_safe(lambda: bool(user.is_librarian_or_higher()), False),
        is_super_librarian=is_super_librarian,
        open_merges_count=_safe(lambda: int(cached_get_counts_by_mode(mode="open") or 0), 0) if is_super_librarian else 0,
    )
