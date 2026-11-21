"""Wire models for the ``community.lexicon.media.book`` XRPC procedures.

Field names are the exact camelCase names published by the lexicon authority
(``did:plc:mtr7qrqtcyseedx3jyr5o7db``), so no aliases are needed. Optional
fields are omitted from responses via ``model_dump(exclude_none=True)``.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Identifier(BaseModel):
    issuer: str
    value: str
    url: str | None = None


class Contributor(BaseModel):
    displayName: str
    identifiers: list[Identifier] = Field(default_factory=list)
    role: str = "A01"  # ONIX Codelist 17: author


class Publisher(BaseModel):
    name: str


class Series(BaseModel):
    name: str


class EditionView(BaseModel):
    title: str
    identifiers: list[Identifier]
    contributors: list[Contributor]
    createdAt: str
    subtitle: str | None = None
    language: str | None = None
    publishedDate: str | None = None
    publisher: Publisher | None = None
    format: str | None = None
    pages: int | None = None
    series: Series | None = None
    bookEdition: str | None = None
    description: str | None = None
    coverUrl: str | None = None


class EditionResults(BaseModel):
    items: list[EditionView]
    hasMore: bool
    total: int | None = None


class ResolveEditionsRequest(BaseModel):
    # The lexicon describes a bag for *one book* and sets no maximum; each entry
    # costs an Infobase round trip, so the cap is one page's worth.
    identifiers: list[Identifier] = Field(min_length=1, max_length=25)
    offset: int = Field(0, ge=0)
    limit: int = Field(25, ge=1, le=100)


class SearchEditionsRequest(BaseModel):
    q: str | None = None
    title: str | None = None
    author: str | None = None
    identifiers: list[Identifier] | None = Field(None, min_length=1, max_length=25)
    offset: int = Field(0, ge=0)
    limit: int = Field(25, ge=1, le=100)
