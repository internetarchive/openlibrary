"""Endpoints behind the cover manager dialog (`<ol-cover-manager>`).

Each doc type gets the same three routes: list its images, upload a new one to
the coverstore (not yet attached), and save the chosen cover.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, HTTPException, Path, UploadFile, status
from pydantic import BaseModel, Field, model_validator

from openlibrary.accounts import get_current_user
from openlibrary.fastapi.auth import AuthenticatedUser, require_authenticated_user
from openlibrary.fastapi.shared.dependencies import ClientIpDep  # noqa: TC001
from openlibrary.plugins.upstream.covers import (
    IMAGE_KINDS,
    apply_cover_changes,
    cover_manager_state,
    image_item,
    image_validator,
    upload_to_coverstore,
)
from openlibrary.plugins.upstream.models import Image
from openlibrary.utils.request_context import site, web_ctx_ip

router = APIRouter(tags=["covers"])

AuthDep = Annotated[AuthenticatedUser, Depends(require_authenticated_user)]
EditionId = Annotated[str, Path(pattern=r"^OL\d+M$")]
WorkId = Annotated[str, Path(pattern=r"^OL\d+W$")]
AuthorId = Annotated[str, Path(pattern=r"^OL\d+A$")]


class CoverAddedBy(BaseModel):
    key: str
    name: str


class CoverItem(BaseModel):
    """One image in the dialog; `id` is "img:<cover id>", or "suggestion:<name>" for an image not stored yet."""

    id: str
    kind: Literal["upload", "archive_cover", "archive_title", "amazon", "wikidata"]
    image_id: int | None = None
    suggestion: str | None = None
    isbn: str | None = None
    thumb: str
    # A larger copy for the dialog's cover column; suggestions use `thumb`.
    preview: str | None = None
    added_by: CoverAddedBy | None = None
    created: str | None = None


class CoverManagerState(BaseModel):
    key: str
    current: str | None
    items: list[CoverItem]


class SaveCoversBody(BaseModel):
    """The new cover is either an image the record has (or just uploaded) or a suggestion to copy in."""

    image_id: int | None = None
    suggestion: str | None = None
    added: list[int] = []
    removed: list[int] = []
    # Why the old cover is being replaced; kept on the edit.
    reason: Literal["wrong", "better", "not_front", "other"] | None = None
    reason_note: str = Field("", max_length=200)

    @model_validator(mode="after")
    def _one_selection(self) -> SaveCoversBody:
        if (self.image_id is None) == (self.suggestion is None):
            raise ValueError("Send one of image_id or suggestion")
        return self


class SaveCoversResponse(BaseModel):
    cover_id: int


def _get_doc(key: str):
    doc = site.get().get(key)
    if not doc or doc.type.key not in IMAGE_KINDS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return doc


def _get_writable_doc(key: str):
    doc = _get_doc(key)
    user = get_current_user()
    if not user or user.is_read_only():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Patron not permitted to change images")
    if not site.get().can_write(key):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")
    return doc, user


def _state(key: str) -> CoverManagerState:
    return CoverManagerState.model_validate(cover_manager_state(_get_doc(key)))


def _upload(key: str, file: UploadFile, client_ip: str) -> CoverItem:
    doc, user = _get_writable_doc(key)
    validator = image_validator()
    try:
        validator.validate_extension(file.filename or "")
        validator.validate_size(file.file)
        validator.validate_image(file.file)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    category = IMAGE_KINDS[doc.type.key].category
    result = upload_to_coverstore(category, key.rsplit("/", maxsplit=1)[-1], data=file.file, author_key=user.key, ip=client_ip)
    if not (image_id := result.get("id")):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.get("message") or result.get("error") or "Upload failed")
    return CoverItem.model_validate(image_item(Image(site.get(), category, int(image_id)), added_by=user))


def _save(key: str, body: SaveCoversBody, client_ip: str) -> SaveCoversResponse:
    doc, user = _get_writable_doc(key)
    try:
        with web_ctx_ip(client_ip):
            cover_id = apply_cover_changes(
                doc,
                image_id=body.image_id,
                suggestion=body.suggestion,
                added=body.added,
                removed=body.removed,
                user=user,
                ip=client_ip,
                reason=body.reason,
                reason_note=body.reason_note,
            )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
    return SaveCoversResponse(cover_id=cover_id)


@router.get("/books/{olid}/covers.json", response_model=CoverManagerState)
def edition_covers(olid: EditionId, _: AuthDep) -> CoverManagerState:
    return _state(f"/books/{olid}")


@router.get("/works/{olid}/covers.json", response_model=CoverManagerState)
def work_covers(olid: WorkId, _: AuthDep) -> CoverManagerState:
    return _state(f"/works/{olid}")


@router.get("/authors/{olid}/photos.json", response_model=CoverManagerState)
def author_photos(olid: AuthorId, _: AuthDep) -> CoverManagerState:
    return _state(f"/authors/{olid}")


@router.post("/books/{olid}/covers/upload.json", response_model=CoverItem)
def edition_cover_upload(olid: EditionId, file: Annotated[UploadFile, File()], client_ip: ClientIpDep, _: AuthDep) -> CoverItem:
    return _upload(f"/books/{olid}", file, client_ip)


@router.post("/works/{olid}/covers/upload.json", response_model=CoverItem)
def work_cover_upload(olid: WorkId, file: Annotated[UploadFile, File()], client_ip: ClientIpDep, _: AuthDep) -> CoverItem:
    return _upload(f"/works/{olid}", file, client_ip)


@router.post("/authors/{olid}/photos/upload.json", response_model=CoverItem)
def author_photo_upload(olid: AuthorId, file: Annotated[UploadFile, File()], client_ip: ClientIpDep, _: AuthDep) -> CoverItem:
    return _upload(f"/authors/{olid}", file, client_ip)


@router.post("/books/{olid}/covers.json", response_model=SaveCoversResponse)
def edition_covers_save(olid: EditionId, body: SaveCoversBody, client_ip: ClientIpDep, _: AuthDep) -> SaveCoversResponse:
    return _save(f"/books/{olid}", body, client_ip)


@router.post("/works/{olid}/covers.json", response_model=SaveCoversResponse)
def work_covers_save(olid: WorkId, body: SaveCoversBody, client_ip: ClientIpDep, _: AuthDep) -> SaveCoversResponse:
    return _save(f"/works/{olid}", body, client_ip)


@router.post("/authors/{olid}/photos.json", response_model=SaveCoversResponse)
def author_photos_save(olid: AuthorId, body: SaveCoversBody, client_ip: ClientIpDep, _: AuthDep) -> SaveCoversResponse:
    return _save(f"/authors/{olid}", body, client_ip)
