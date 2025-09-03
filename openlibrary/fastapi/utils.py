from __future__ import annotations

from typing import Any
from urllib.parse import unquote

from fastapi import Request
from fastapi.templating import Jinja2Templates

from infogami import config as ig_config  # type: ignore
from infogami.infobase import client as ib_client  # type: ignore

# Use existing Infogami client to talk to Infobase using configured parameters
from infogami.utils.view import render_template
from openlibrary.plugins.worksearch.code import (
    get_remembered_layout,
)

templates: Jinja2Templates = Jinja2Templates(directory="openlibrary/fastapi/templates")
templates.env.add_extension('jinja2.ext.i18n')
templates.env.install_null_translations(newstyle=True)


def get_jinja_context(
    request: Request,
    user: dict | None = None,
    page: Any | None = None,
    title: str | None = None,
):
    return {
        # New templates use this ctx
        "ctx": {
            "title": title,
            "description": "",
            "robots": "index, follow",
            "links": [],
            "metatags": [],
            "features": ["dev"],
            "path": request.url.path,
            "user": user,
        },
        "request": request,
        "page": page,
        "render_template": render_template,
        "get_remembered_layout": get_remembered_layout,
        "homepath": lambda: "",
        "get_flash_messages": list,
        "get_internet_archive_id": lambda x: "@openlibrary",
        "cached_get_counts_by_mode": lambda mode: 0,
    }


def get_site(auth_token: str | None = None) -> ib_client.Site:
    """Create an Infobase client Site using already-loaded config.

    This avoids calling back into the legacy WSGI app and uses existing Python
    facilities to load objects.
    """
    conn = ib_client.connect(**ig_config.infobase_parameters)
    if auth_token:
        auth_token = unquote(auth_token)
        conn.set_auth_token(auth_token)
    return ib_client.Site(conn, ig_config.site or "openlibrary.org")


def get_user_from_request(request: Request):
    # TODO: Turn into a fastapi dependency
    if auth_token := request.cookies.get(ig_config.login_cookie_name):
        site = get_site(auth_token)
        d = site._request('/account/get_user')
        u = ib_client.create_thing(site, d['key'], d)
    else:
        u = None
    return u
