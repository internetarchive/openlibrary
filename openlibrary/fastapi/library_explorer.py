"""`/explore`, the Library Explorer page."""

from fastapi import APIRouter

from openlibrary.core.jinja import render_jinja_template
from openlibrary.core.shell.request import PageMeta
from openlibrary.fastapi.shared.site_page import SitePage, SitePageRoute
from openlibrary.i18n import gettext as _
from openlibrary.plugins.upstream.utils import vue_component_html

pages = APIRouter(route_class=SitePageRoute)


@pages.get("/explore")
async def library_explorer() -> SitePage:
    # TODO: Retire the web.py `library_explorer` handler (it still serves /explore
    # in production) once production routes /explore here.
    body = render_jinja_template("library_explorer.html.jinja", vue_component_html=vue_component_html)
    return SitePage(body, page=PageMeta(title=_("Library Explorer"), bodyclass=("full-width", "library-explorer")))
