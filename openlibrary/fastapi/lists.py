from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Path, Query, Response, HTTPException
from fastapi.responses import Response
from openlibrary.utils.request_context import site
from openlibrary.core import formats

router = APIRouter()


async def lists_delete(filename: Annotated[str, Path()]) -> Response:
    return Response(status_code=200)


async def lists_json():
    pass


async def list_view_json():
    pass


async def list_seeds():
    pass


def fastapi_make_collection(request: Request, size: int, entries: list, limit: int, offset: int, key: str | None = None) -> dict:
    d = {
        "size": size,
        "start": offset,
        "end": offset + limit,
        "entries": entries,
        "links": {
            "self": f"{request.url.path}{f"?{request.url.query}" if request.url.query else ""}",
        },
    }

    if offset + len(entries) < size:
        d["links"]["next"] = str(request.url.include_query_params(limit=limit, offset=offset + limit))

    if offset > 0:
        d["links"]["prev"] = str(request.url.include_query_params(limit=limit, offset=max(0, offset - limit)))

    if key:
        d["links"]["list"] = key

    return d


def _get_editions_response(request: Request, key: str, ext: str, limit: int, offset: int) -> Response:
    lst = site.get().get(key)
    if not lst:
        raise HTTPException(status_code=404, detail="Editions not found")

    all_editions = list(lst.get_editions())
    editions = all_editions[offset : offset + limit]

    response_data = fastapi_make_collection(
        request=request,
        size=len(all_editions),
        entries=[e.dict() for e in editions],
        limit=limit,
        offset=offset,
        key=key,
    )

    encoding = "yml" if ext in ("yml", "yaml") else "json"
    content_type = 'text/yaml; charset="utf-8"' if encoding == "yml" else "application/json"

    content = formats.dump(response_data, encoding)
    return Response(content=content, media_type=content_type)


@router.get("/lists/{olid}/editions.{ext}")
def read_list_editions(
    request: Request,
    olid: str = Path(..., pattern=r"^OL\d+L$"),
    ext: Literal["json", "yml", "yaml"] = Path(...),
    limit: int = Query(50, ge=1, description="Number of editions to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
    key = f"/lists/{olid}"
    return _get_editions_response(request, key, ext, limit, offset)


@router.get("/people/{username}/lists/{olid}/editions.{ext}")
def read_people_list_editions(
    request: Request,
    username: str = Path(...),
    olid: str = Path(..., pattern=r"^OL\d+L$"),
    ext: Literal["json", "yml", "yaml"] = Path(...),
    limit: int = Query(50, ge=1),
    offset: int = Query(0, ge=0),
):
    key = f"/people/{username}/lists/{olid}"
    return _get_editions_response(request, key, ext, limit, offset)


@router.get("/series/{olid}/editions.{ext}")
def read_series_editions(
    request: Request,
    olid: str = Path(..., pattern=r"^OL\d+L$"),
    ext: Literal["json", "yml", "yaml"] = Path(...),
    limit: int = Query(50, ge=1),
    offset: int = Query(0, ge=0),
):
    key = f"/series/{olid}"
    return _get_editions_response(request, key, ext, limit, offset)


@router.get("/people/{username}/series/{olid}/editions.{ext}")
def read_people_series_editions(
    request: Request,
    username: str = Path(...),
    olid: str = Path(..., pattern=r"^OL\d+L$"),
    ext: Literal["json", "yml", "yaml"] = Path(...),
    limit: int = Query(50, ge=1),
    offset: int = Query(0, ge=0),
):
    key = f"/people/{username}/series/{olid}"
    return _get_editions_response(request, key, ext, limit, offset)


async def list_subjects_json():
    pass
