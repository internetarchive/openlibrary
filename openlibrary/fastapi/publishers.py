from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path

from openlibrary.core.helpers import commify
from openlibrary.core.jinja import render_jinja_template
from openlibrary.core.shell.request import PageMeta
from openlibrary.fastapi.services.subject_service import (
    BaseSubjectRequestParams,
    fetch_subject_data,
)
from openlibrary.fastapi.shared.site_page import SitePage, SitePageRoute
from openlibrary.i18n import gettext as _
from openlibrary.plugins.openlibrary.partials import query_carousel
from openlibrary.plugins.worksearch.subjects import get_subject_async

router = APIRouter()
pages = APIRouter(route_class=SitePageRoute)


@router.get("/publishers/{key:path}.json")
async def publisher_json(
    key: Annotated[str, Path()],
    params: Annotated[BaseSubjectRequestParams, Depends()],
) -> dict[str, Any]:
    # Replace underscores with spaces in the key
    processed_key = key.replace("_", " ")
    return await fetch_subject_data(
        key=processed_key,
        params=params,
        path_prefix="/publishers",
    )


@pages.get("/publishers")
async def publishers_index() -> SitePage:
    # TODO: Retire the web.py `index` handler (it still serves /publishers in
    # production) once production routes /publishers here.
    return SitePage(render_jinja_template("publishers/index.html.jinja"))


@pages.get("/publishers/{name}")
async def publisher_page(name: str) -> SitePage:
    # TODO: Retire the web.py `publishers` handler (it still serves
    # /publishers/<name> in production) once production routes it here.
    key = f"/publishers/{name.replace('_', ' ')}"
    page = await get_subject_async(key, details=True, request_label="SUBJECT_ENGINE_PAGE")

    if not page or page.work_count == 0:
        body = render_jinja_template("publishers/notfound.html.jinja", key=key)
        return SitePage(body, status_code=404)

    body = render_jinja_template(
        "publishers/view.html.jinja",
        page=page,
        commify=commify,
        query_carousel=query_carousel,
    )
    return SitePage(body, page=PageMeta(title=_("Publisher: %(name)s", name=page.name)))
