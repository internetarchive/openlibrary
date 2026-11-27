"""`/barcodescanner`, the experimental barcode scanner page."""

from fastapi import APIRouter

from openlibrary.core.jinja import render_jinja_template
from openlibrary.core.shell.request import PageMeta
from openlibrary.fastapi.shared.site_page import SitePage, SitePageRoute
from openlibrary.i18n import gettext as _
from openlibrary.plugins.upstream.utils import vue_component_html

pages = APIRouter(route_class=SitePageRoute)


@pages.get("/barcodescanner")
async def barcodescanner() -> SitePage:
    # TODO: Retire the web.py `scan` handler (it still serves /barcodescanner
    # in production) once production routes /barcodescanner here.
    body = render_jinja_template("barcodescanner.html.jinja", vue_component_html=vue_component_html)
    return SitePage(body, page=PageMeta(title=_("Barcode Scanner (Beta)"), show_ol_shell=False))
