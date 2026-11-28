"""FastAPI endpoint for merging authors.

Migrated from openlibrary.plugins.upstream.merge_authors.merge_authors_json.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from infogami.infobase.client import ClientException
from openlibrary.fastapi.auth import LibrarianDep  # noqa: TC001
from openlibrary.fastapi.shared.dependencies import ClientIpDep  # noqa: TC001
from openlibrary.plugins.upstream.edits import perform_merge_update
from openlibrary.plugins.upstream.merge_authors import (
    AuthorMergeEngine,
    AuthorRedirectEngine,
)
from openlibrary.utils.request_context import web_ctx_ip

router = APIRouter(tags=["merge-authors"])


class MergeAuthorsBody(BaseModel):
    master: str
    duplicates: list[str]
    mrid: int | None = None
    comment: str | None = None
    olids: str = ""


def _merge(master: str, duplicates: list[str], client_ip: str) -> Any:
    with web_ctx_ip(client_ip):
        return AuthorMergeEngine(AuthorRedirectEngine()).merge(master, duplicates)


@router.post("/authors/merge.json")
async def merge_authors_json(user: LibrarianDep, client_ip: ClientIpDep, data: MergeAuthorsBody) -> Any:
    try:
        # The Infobase merge is sync I/O, so keep it off the event loop.
        merge_result = await run_in_threadpool(_merge, data.master, data.duplicates, client_ip)
    except ClientException as e:
        raise HTTPException(
            status_code=400,
            detail=e.get_data() or str(e),
        )

    await perform_merge_update(username=user.username, mrid=data.mrid, olids=data.olids, comment=data.comment)

    return merge_result
