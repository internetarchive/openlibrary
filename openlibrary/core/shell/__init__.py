"""Data layer for the Jinja site shell (``openlibrary/templates/shell/``).

The shell is the chrome every page shares: the page wrapper, head, header,
footer, alert/banner/stats and the header-only nav macros. Each region has a
frozen context object built here; ``LayoutContext`` composes them for
``shell/base.html.jinja``.
"""

from openlibrary.core.shell.chrome import AnnouncementBanner, can_show_librarian_tools
from openlibrary.core.shell.context import LayoutContext, SiteLayoutTemplate
from openlibrary.core.shell.head import HeadContext, SentryContext
from openlibrary.core.shell.header import HeaderContext, HeaderUser
from openlibrary.core.shell.nav import BROWSE_FEATURED_COUNT, NavLink, browse_links
from openlibrary.core.shell.search_modal import SearchModalContext

__all__ = [
    "BROWSE_FEATURED_COUNT",
    "AnnouncementBanner",
    "HeadContext",
    "HeaderContext",
    "HeaderUser",
    "LayoutContext",
    "NavLink",
    "SearchModalContext",
    "SentryContext",
    "SiteLayoutTemplate",
    "browse_links",
    "can_show_librarian_tools",
]
