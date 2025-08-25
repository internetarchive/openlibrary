from __future__ import annotations

from typing import Any

from fastapi import Request

# Use existing Infogami client to talk to Infobase using configured parameters
from infogami.utils.view import render_template
from openlibrary.plugins.worksearch.code import (
    get_remembered_layout,
)


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
