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
from openlibrary.plugins.upstream.edits import process_merge_request
from openlibrary.plugins.upstream.merge_authors import (
    AuthorMergeEngine,
    AuthorRedirectEngine,
)
from openlibrary.utils.request_context import req_context, web_ctx_ip
from openlibrary.utils.retry import MaxRetriesExceeded, RetryStrategy

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

        def update_request() -> None:
            if data.mrid:
                rtype = "update-request"
                update_data: dict[str, Any] = {"action": "approve", "mrid": data.mrid}
            else:
                rtype = "create-request"
                update_data = {"mr_type": 2, "olids": data.olids, "action": "create-merged"}
            if data.comment:
                update_data["comment"] = data.comment
            process_merge_request(rtype, update_data)

        try:
            RetryStrategy(
                [ClientException],
                max_retries=5,
                delay=2,
            )(update_request)
        except MaxRetriesExceeded as e:
            raise HTTPException(
                status_code=400,
                detail=str(e.last_exception),
            )

    return merge_result
