"""FastAPI endpoint for merging authors.

Migrated from openlibrary.plugins.upstream.merge_authors.merge_authors_json.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from infogami.infobase.client import ClientException
from openlibrary.fastapi.auth import LibrarianDep  # noqa: TC001
from openlibrary.plugins.upstream.edits import perform_merge_update
from openlibrary.plugins.upstream.merge_authors import (
    AuthorMergeEngine,
    AuthorRedirectEngine,
)
from openlibrary.utils.request_context import req_context, web_ctx_ip
from openlibrary.utils.retry import MaxRetriesExceeded

router = APIRouter(tags=["merge-authors"])


class MergeAuthorsBody(BaseModel):
    master: str
    duplicates: list[str]
    mrid: str | None = None
    comment: str | None = None
    olids: str = ""


@router.post("/authors/merge.json")
def merge_authors_json(_: LibrarianDep, data: MergeAuthorsBody) -> Any:
    with web_ctx_ip(req_context.get().x_forwarded_for or "127.0.0.1"):
        try:
            engine = AuthorMergeEngine(AuthorRedirectEngine())
            merge_result = engine.merge(data.master, data.duplicates)
        except ClientException as e:
            raise HTTPException(
                status_code=400,
                detail=json.loads(e.json),
            )

        try:
            perform_merge_update(mrid=data.mrid, olids=data.olids, comment=data.comment)
        except MaxRetriesExceeded as e:
            raise HTTPException(
                status_code=400,
                detail=str(e.last_exception),
            )

    return merge_result
