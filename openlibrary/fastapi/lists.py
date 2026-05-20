from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any, Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, Request, status
from pydantic import BaseModel

from infogami.infobase import client
from openlibrary.accounts import get_current_user
from openlibrary.fastapi.auth import AuthenticatedUser, require_authenticated_user
from openlibrary.plugins.openlibrary import lists as legacy_lists
from openlibrary.plugins.openlibrary.lists import (
    ListEditionsModel,
    ListSubjectsModel,
    SpamListError,
    get_list,
    get_list_editions,
    get_list_seeds,
    get_list_subjects,
)
from openlibrary.plugins.openlibrary.lists import list_seeds as _LegacyListSeeds
from openlibrary.plugins.openlibrary.lists import lists_delete as _LegacyListsDelete
from openlibrary.utils.request_context import site, web_ctx_ip

# Exposed as a module-level alias so it can be monkeypatched by tests.
get_list = legacy_lists.get_list

if TYPE_CHECKING:
    from starlette.datastructures import URL

router = APIRouter(tags=["lists"])


class ListsJsonLinks(BaseModel):
    """Pagination links for a lists.json response."""

    self: str
    next: str | None = None
    prev: str | None = None


class ListPreviewEntry(BaseModel):
    """A single list entry in a lists.json response."""

    url: str
    full_url: str
    name: str
    seed_count: int
    last_update: str | None = None


class ListsJsonResponse(BaseModel):
    """Response model for GET /<entity>/lists.json endpoints."""

    links: ListsJsonLinks
    size: int
    entries: list[ListPreviewEntry]


class CreateListBody(BaseModel):
    """Request body for creating a new list."""

    name: str = ""
    description: str = ""
    tags: list[str] = []
    seeds: list[dict[str, Any] | str] = []


class CreateListResponse(BaseModel):
    """Response model for POST /people/{username}/lists.json.

    Uses `extra="allow"` to preserve any additional fields returned
    by the underlying `site.save()` call (e.g. ``type``, ``created``,
    ``last_modified``) for backward compatibility.
    """

    key: str
    revision: int

    model_config = {"extra": "allow"}


def _get_list_or_404(key: str, raw: bool) -> dict:
    """Fetch a list by key and raise 404 if not found or deleted."""
    if not (lst := get_list(key, raw=raw)) or lst.get("type", {}).get("key") == "/type/delete":
        raise HTTPException(status_code=404, detail="List not found")
    return lst


def _process_list_delete(key: str) -> dict:
    """Shared delete logic for both route variants."""

    user = get_current_user()

    if user and not user.is_admin() and (user.key and not key.startswith(user.key)):
        raise HTTPException(status_code=403, detail="Permission denied.")

    doc = site.get().get(key)
    if doc is None or doc.type.key != "/type/list":
        raise HTTPException(status_code=404, detail="Not found.")

    try:
        with web_ctx_ip():
            _LegacyListsDelete.process_delete(doc, key)
    except client.ClientException as e:
        raise HTTPException(
            status_code=int(e.status.split()[0]),
            detail=e.json.decode("utf-8") if isinstance(e.json, bytes) else e.json,
        )

    return {"status": "ok"}


UsernamePath = Annotated[str, Path(description="The patron's username")]
RawFlag = Annotated[bool, Query(alias="_raw", description="Return raw database record")]
ListOLID = Annotated[str, Path(description="The OLID, e.g. OL123L", pattern=r"OL\d+L")]
ListCategory = Annotated[Literal["lists", "series"], Path(description="List category")]


@router.get("/people/{username}/{category}/{list_id}.json")
def list_view_json_user(
    username: UsernamePath,
    category: ListCategory,
    list_id: ListOLID,
    raw: RawFlag = False,
) -> dict:
    """
    Returns JSON metadata for a user-owned list or series.

    Examples:
    /people/mekBot/lists/OL123L.json
    /people/mekBot/series/OL123L.json
    """
    key = f"/people/{username}/{category}/{list_id}"
    return _get_list_or_404(key, raw=raw)


@router.get("/lists/{list_id}.json")
@router.get("/series/{list_id}.json")
def list_view_json_public(
    request: Request,
    list_id: ListOLID,
    raw: RawFlag = False,
) -> dict:
    """
    Returns JSON metadata for a public list or series.

    Examples:
    /lists/OL456L.json
    /series/OL789L.json
    """
    category = request.url.path.split("/")[1]
    key = f"/{category}/{list_id}"
    return _get_list_or_404(key, raw=raw)


@router.post("/people/{username}/lists/{list_id}/delete.json")
def lists_delete(
    username: UsernamePath,
    list_id: ListOLID,
    _: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
) -> dict:
    """Delete a list owned by the given user."""
    return _process_list_delete(f"/people/{username}/lists/{list_id}")


@router.post("/lists/{list_id}/delete.json")
def lists_delete_no_prefix(
    list_id: ListOLID,
    _: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
) -> dict:
    """Delete a list (legacy path without username prefix)."""
    return _process_list_delete(f"/lists/{list_id}")


class ListsJsonPagination:
    """Request + pagination dependency for lists.json endpoints."""

    def __init__(
        self,
        request: Request,
        offset: Annotated[int, Query(ge=0, description="Pagination offset")] = 0,
        limit: Annotated[int, Query(ge=0, le=100, description="Number of items to return (max 100)")] = 50,
    ):
        self.request: Request = request
        self.offset: int = offset
        self.limit: int = limit


CommonListsJsonPagination = Annotated[ListsJsonPagination, Depends()]


def _lists_json_data(
    seed_path: str,
    pagination: ListsJsonPagination,
) -> ListsJsonResponse:
    """Shared helper for lists.json endpoints."""
    data = legacy_lists.lists_json.get_lists_data(
        seed_path,
        limit=pagination.limit,
        offset=pagination.offset,
        query_path=pagination.request.url.path,
    )
    if data is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return ListsJsonResponse(**data)


@router.get("/people/{username}/lists.json", response_model=ListsJsonResponse, response_model_exclude_none=True)
def lists_json_people(username: str, pagination: CommonListsJsonPagination) -> ListsJsonResponse:
    return _lists_json_data(f"/people/{username}", pagination)


@router.get("/books/OL{edition_id}M/lists.json", response_model=ListsJsonResponse, response_model_exclude_none=True)
def lists_json_books(edition_id: int, pagination: CommonListsJsonPagination) -> ListsJsonResponse:
    return _lists_json_data(f"/books/OL{edition_id}M", pagination)


@router.get("/works/OL{work_id}W/lists.json", response_model=ListsJsonResponse, response_model_exclude_none=True)
def lists_json_works(work_id: int, pagination: CommonListsJsonPagination) -> ListsJsonResponse:
    return _lists_json_data(f"/works/OL{work_id}W", pagination)


@router.get("/authors/OL{author_id}A/lists.json", response_model=ListsJsonResponse, response_model_exclude_none=True)
def lists_json_authors(author_id: int, pagination: CommonListsJsonPagination) -> ListsJsonResponse:
    return _lists_json_data(f"/authors/OL{author_id}A", pagination)


@router.get("/subjects/{subject_key:path}/lists.json", response_model=ListsJsonResponse, response_model_exclude_none=True)
def lists_json_subjects(subject_key: str, pagination: CommonListsJsonPagination) -> ListsJsonResponse:
    return _lists_json_data(f"/subjects/{subject_key}", pagination)


@router.post("/people/{username}/lists.json", response_model=CreateListResponse)
def lists_json_post(
    username: str,
    body: CreateListBody,
    _: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
) -> dict[str, Any]:
    current_site = site.get()
    user_key = f"/people/{username}"
    user = current_site.get(user_key)

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    if not current_site.can_write(user_key):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied.",
        )

    try:
        with web_ctx_ip():
            result = legacy_lists.lists_json.process_new_list(user, body.model_dump(), current_site)
    except SpamListError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied.",
        )
    except client.ClientException as e:
        status_code = int(e.status.split()[0])
        raise HTTPException(
            status_code=status_code,
            detail=str(e),
        )

    return result


def _get_list_seeds_or_404(key: str) -> dict:
    lst = get_list_seeds(key)
    if lst is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="List or Series not found")
    return lst


def _update_list_seeds(key: str, payload: dict) -> dict:
    s = site.get()
    lst = s.get(key)

    if lst is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="List or Series not found")

    if not s.can_write(key):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied.")

    try:
        # Pass the payload safely directly to the legacy processor
        data = {"add": payload.get("add", []), "remove": payload.get("remove", [])}
        return _LegacyListSeeds.process_seeds_update(lst, data, key)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/people/{username}/lists/{olid}/seeds.json")
def list_seeds_json_user(username: UsernamePath, olid: ListOLID) -> dict:
    return _get_list_seeds_or_404(f"/people/{username}/lists/{olid}")


@router.get("/people/{username}/series/{olid}/seeds.json")
def series_seeds_json_user(username: UsernamePath, olid: ListOLID) -> dict:
    return _get_list_seeds_or_404(f"/people/{username}/series/{olid}")


@router.get("/lists/{olid}/seeds.json")
def list_seeds_json_public(olid: ListOLID) -> dict:
    return _get_list_seeds_or_404(f"/lists/{olid}")


@router.get("/series/{olid}/seeds.json")
def series_seeds_json_public(olid: ListOLID) -> dict:
    return _get_list_seeds_or_404(f"/series/{olid}")


@router.post("/people/{username}/lists/{olid}/seeds.json")
def update_list_seeds_json_user(
    username: UsernamePath, olid: ListOLID, payload: Annotated[dict, Body(...)], _: Annotated[AuthenticatedUser, Depends(require_authenticated_user)]
) -> dict:
    return _update_list_seeds(f"/people/{username}/lists/{olid}", payload)


@router.post("/people/{username}/series/{olid}/seeds.json")
def update_series_seeds_json_user(
    username: UsernamePath, olid: ListOLID, payload: Annotated[dict, Body(...)], _: Annotated[AuthenticatedUser, Depends(require_authenticated_user)]
) -> dict:
    return _update_list_seeds(f"/people/{username}/series/{olid}", payload)


@router.post("/lists/{olid}/seeds.json")
def update_list_seeds_json_public(
    olid: ListOLID, payload: Annotated[dict, Body(...)], _: Annotated[AuthenticatedUser, Depends(require_authenticated_user)]
) -> dict:
    return _update_list_seeds(f"/lists/{olid}", payload)


@router.post("/series/{olid}/seeds.json")
def update_series_seeds_json_public(
    olid: ListOLID, payload: Annotated[dict, Body(...)], _: Annotated[AuthenticatedUser, Depends(require_authenticated_user)]
) -> dict:
    return _update_list_seeds(f"/series/{olid}", payload)


class GetListEditionsParams:
    def __init__(
        self,
        request: Request,
        limit: Annotated[int, Query(ge=0, description="Number of items to return")] = 50,
        offset: Annotated[int, Query(ge=0, description="Pagination offset")] = 0,
    ):
        self.url: URL = request.url
        self.limit: int = limit
        self.offset: int = offset


def _get_editions_response(key: str, params: GetListEditionsParams) -> ListEditionsModel:
    if response_data := get_list_editions(key=key, url=params.url, offset=params.offset, limit=params.limit):
        return response_data

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Editions not found")


CommonPagination = Annotated[GetListEditionsParams, Depends()]


@router.get("/lists/{olid}/editions.json")
def list_editions_json(olid: ListOLID, params: CommonPagination) -> ListEditionsModel:
    """
    Get paginated editions for a public list.
    """
    key = f"/lists/{olid}"
    return _get_editions_response(key, params)


@router.get("/people/{username}/lists/{olid}/editions.json")
def list_editions_json_people(username: UsernamePath, olid: ListOLID, params: CommonPagination) -> ListEditionsModel:
    """
    Get paginated editions for a specific user's list.
    """
    key = f"/people/{username}/lists/{olid}"
    return _get_editions_response(key, params)


@router.get("/series/{olid}/editions.json")
def series_editions_json(olid: ListOLID, params: CommonPagination) -> ListEditionsModel:
    """
    Get paginated editions for a specific series.
    """
    key = f"/series/{olid}"
    return _get_editions_response(key, params)


@router.get("/people/{username}/series/{olid}/editions.json")
def series_editions_json_people(username: UsernamePath, olid: ListOLID, params: CommonPagination) -> ListEditionsModel:
    """
    Get paginated editions for a specific user's series.
    """
    key = f"/people/{username}/series/{olid}"
    return _get_editions_response(key, params)


CommonSubjectsLimit = Annotated[int, Query(ge=0, description="Number of subjects to return")]


@router.get("/people/{username}/lists/{olid}/subjects.json")
def list_subjects_json_user(username: UsernamePath, olid: ListOLID, limit: CommonSubjectsLimit = 20) -> ListSubjectsModel:
    key = f"/people/{username}/lists/{olid}"
    if data := get_list_subjects(key, limit):
        return data
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="List not found")


@router.get("/people/{username}/series/{olid}/subjects.json")
def list_subjects_json_user_series(username: UsernamePath, olid: ListOLID, limit: CommonSubjectsLimit = 20) -> ListSubjectsModel:
    key = f"/people/{username}/series/{olid}"
    if data := get_list_subjects(key, limit):
        return data
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="List not found")


@router.get("/lists/{olid}/subjects.json")
def list_subjects_json_public(olid: ListOLID, limit: CommonSubjectsLimit = 20) -> ListSubjectsModel:
    key = f"/lists/{olid}"
    if data := get_list_subjects(key, limit):
        return data
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="List not found")


@router.get("/series/{olid}/subjects.json")
def list_subjects_json_series(olid: ListOLID, limit: CommonSubjectsLimit = 20) -> ListSubjectsModel:
    key = f"/series/{olid}"
    if data := get_list_subjects(key, limit):
        return data
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="List not found")
