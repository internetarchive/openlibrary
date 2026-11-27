"""`/tags`, `/tag/add` and `/tags/OLnT`, the tag pages."""

from __future__ import annotations

import re
from typing import Annotated
from urllib.parse import quote_plus

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse

from openlibrary.accounts import get_current_user
from openlibrary.core.helpers import safeint, urlsafe
from openlibrary.core.jinja import render_jinja_template
from openlibrary.core.models import Tag
from openlibrary.core.shell.request import PageMeta
from openlibrary.fastapi.shared.site_page import SitePage, SitePageRoute
from openlibrary.i18n import gettext as _
from openlibrary.plugins.upstream import addtag
from openlibrary.plugins.upstream.addtag import TAG_TYPES
from openlibrary.utils.request_context import site

pages = APIRouter(route_class=SitePageRoute)

TAG_KEY = re.compile(r"OL\d+T")
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


@pages.get("/tag/add")
def add_tag(name: str = "") -> Response:
    # TODO: Retire the web.py `addtag.GET` handler (it still serves /tag/add in
    # production) once production routes it here. The POST stays on web.py.
    if not (patron := get_current_user()):
        return RedirectResponse("/account/login?redirect=/tag/add", status_code=status.HTTP_303_SEE_OTHER)

    if not addtag.can_create_tag(patron):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Permission denied to add tags")

    return SitePage(
        addtag.render_tag_form(name=name),
        page=PageMeta(title=_("Add a tag"), robots="noindex,nofollow"),
    )


@pages.get("/tags/{key}")
@pages.get("/tags/{key}/{slug}")
def tag_page(request: Request, key: str, slug: str = "") -> Response:
    # TODO: Retire the web.py `tag_view` handler (it still serves /tags/OLnT in
    # production) once production routes it here.
    if not TAG_KEY.fullmatch(key):
        if key == "-":
            return _search_redirect(slug, request)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")

    tag = site.get().get(f"/tags/{key}")
    if tag is None or tag.type.key != "/type/tag":
        return _notfound(f"/tags/{key}")

    # The canonical URL has the tag's name as a slug, as web.py's readable URLs do.
    if slug != (canonical := urlsafe((tag.name or "").strip()) or "untitled"):
        query = f"?{request.url.query}" if request.url.query else ""
        return RedirectResponse(f"/tags/{key}/{quote_plus(canonical)}{query}", status_code=status.HTTP_303_SEE_OTHER)

    return SitePage(addtag.render_tag_view(tag), page=PageMeta(title=tag.name))


def _search_redirect(spec: str, request: Request) -> Response:
    """Resolve `/tags/-/{tag_type}:{name}` to a tag's page, as web.py's `tag_search` does."""
    tag_type, _, name = spec.partition(":")
    if matches := Tag.find(name, tag_type=tag_type):
        query = f"?{request.url.query}" if request.url.query else ""
        return RedirectResponse(f"{matches[0]}{query}", status_code=status.HTTP_303_SEE_OTHER)
    return _notfound(f"/tags/-/{spec}")


def _notfound(path: str) -> SitePage:
    return SitePage(
        render_jinja_template("notfound.html.jinja", path=path),
        page=PageMeta(title=_("%(path)s is not found", path=path)),
        status_code=status.HTTP_404_NOT_FOUND,
    )
