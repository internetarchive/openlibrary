"""`/tags`, the list of curated tags."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from openlibrary.core.helpers import safeint
from openlibrary.core.shell.request import PageMeta
from openlibrary.fastapi.shared.site_page import SitePage, SitePageRoute
from openlibrary.i18n import gettext as _
from openlibrary.plugins.upstream import addtag
from openlibrary.plugins.upstream.addtag import TAG_TYPES
from openlibrary.utils.request_context import site

pages = APIRouter(route_class=SitePageRoute)

PAGE_SIZE = 20


@pages.get("/tags")
def tags_index(
    tag_type: Annotated[str | None, Query(alias="type")] = None,
    page: str = "1",
) -> SitePage:
    # TODO: Retire the web.py `tags_index` handler (it still serves /tags in
    # production) once production routes /tags here.
    page_num = max(1, safeint(page, 1))
    tag_type = tag_type if tag_type in TAG_TYPES else None

    query = {"type": "/type/tag", "limit": PAGE_SIZE + 1, "offset": (page_num - 1) * PAGE_SIZE}
    if tag_type:
        query["tag_type"] = tag_type

    tag_keys = site.get().things(query)
    has_next = len(tag_keys) > PAGE_SIZE
    tags = site.get().get_many(tag_keys[:PAGE_SIZE]) if tag_keys else []

    return SitePage(
        addtag.render_tags_index(tags=tags, page=page_num, has_next=has_next, tag_type=tag_type),
        page=PageMeta(title=_("Tags")),
    )
