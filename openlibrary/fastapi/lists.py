from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Path, Query, Request, Response

from openlibrary.core import formats
from openlibrary.utils.request_context import site

router = APIRouter()


async def lists_delete(filename: Annotated[str, Path()]) -> Response:
    return Response(status_code=200)


async def lists_json():
    pass


async def list_view_json():
    pass


async def list_seeds():
    pass


def fastapi_make_collection(
    request: Request,
    size: int,
    entries: list,
    limit: int,
    offset: int,
    key: str | None = None,
) -> dict[str, Any]:
    def _get_relative_url(url: Any) -> str:
        return f"{url.path}?{url.query}" if url.query else url.path

    links: dict[str, str] = {
        "self": _get_relative_url(request.url),
    }

    d: dict[str, Any] = {
        "size": size,
        "start": offset,
        "end": offset + limit,
        "entries": entries,
        "links": links,
    }

    if offset + len(entries) < size:
        next_url = request.url.include_query_params(limit=limit, offset=offset + limit)
        links["next"] = _get_relative_url(next_url)

    if offset > 0:
        prev_url = request.url.include_query_params(limit=limit, offset=max(0, offset - limit))
        links["prev"] = _get_relative_url(prev_url)

    if key:
        links["list"] = key

    return d


def _get_editions_response(request: Request, key: str, ext: str, limit: int, offset: int) -> Response:
    lst = site.get().get(key)
    if not lst:
        raise HTTPException(status_code=404)

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

    encoding: Literal["json", "yml"] = "yml" if ext in ("yml", "yaml") else "json"
    content_type = 'text/yaml; charset="utf-8"' if encoding == "yml" else "application/json"

    content = formats.dump(response_data, encoding)
    return Response(content=content, media_type=content_type)


@router.get("/lists/{olid}/editions.{ext}")
def read_list_editions(
    request: Request,
    olid: Annotated[str, Path(pattern=r"^OL\d+L$")],
    ext: Annotated[Literal["json", "yml", "yaml"], Path()],
    limit: Annotated[int, Query(ge=1, description="Number of editions to return")] = 50,
    offset: Annotated[int, Query(ge=0, description="Pagination offset")] = 0,
):
    key = f"/lists/{olid}"
    return _get_editions_response(request, key, ext, limit, offset)


@router.get("/people/{username}/lists/{olid}/editions.{ext}")
def read_people_list_editions(
    request: Request,
    username: Annotated[str, Path()],
    olid: Annotated[str, Path(pattern=r"^OL\d+L$")],
    ext: Annotated[Literal["json", "yml", "yaml"], Path()],
    limit: Annotated[int, Query(ge=1)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    key = f"/people/{username}/lists/{olid}"
    return _get_editions_response(request, key, ext, limit, offset)


@router.get("/series/{olid}/editions.{ext}")
def read_series_editions(
    request: Request,
    olid: Annotated[str, Path(pattern=r"^OL\d+L$")],
    ext: Annotated[Literal["json", "yml", "yaml"], Path()],
    limit: Annotated[int, Query(ge=1)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    key = f"/series/{olid}"
    return _get_editions_response(request, key, ext, limit, offset)


@router.get("/people/{username}/series/{olid}/editions.{ext}")
def read_people_series_editions(
    request: Request,
    username: Annotated[str, Path()],
    olid: Annotated[str, Path(pattern=r"^OL\d+L$")],
    ext: Annotated[Literal["json", "yml", "yaml"], Path()],
    limit: Annotated[int, Query(ge=1)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    key = f"/people/{username}/series/{olid}"
    return _get_editions_response(request, key, ext, limit, offset)


async def list_subjects_json():
    pass
