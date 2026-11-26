"""`/about/team`, the Open Library team page."""

from fastapi import APIRouter

from openlibrary.core.jinja import render_jinja_template
from openlibrary.core.shell.request import PageMeta
from openlibrary.fastapi.shared.site_page import SitePage, SitePageRoute
from openlibrary.i18n import gettext as _

pages = APIRouter(route_class=SitePageRoute)


@pages.get("/about/team")
async def team() -> SitePage:
    # TODO: Retire the web.py `team` handler (it still serves /about/team in
    # production) once production routes /about/team here.
    body = render_jinja_template("about/index.html.jinja")
    return SitePage(body, page=PageMeta(title=_("The Open Library Team"), cssfile="team"))
