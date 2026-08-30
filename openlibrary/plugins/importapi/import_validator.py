from typing import Annotated, Any, Final, TypeVar

from annotated_types import MinLen
from pydantic import BaseModel, ValidationError, model_validator

from openlibrary.catalog.add_book import (
    SUSPECT_AUTHOR_NAMES,
    SUSPECT_DATE_EXEMPT_SOURCES,
    SUSPECT_PUBLICATION_DATES,
)

T = TypeVar("T")

NonEmptyList = Annotated[list[T], MinLen(1)]
NonEmptyStr = Annotated[str, MinLen(1)]

STRONG_IDENTIFIERS: Final = {"isbn_10", "isbn_13", "lccn"}


class Author(BaseModel):
    name: NonEmptyStr


class CompleteBook(BaseModel):
    """
    The model for a complete book, plus source_records.

    A complete book has title, authors, and publish_date, as well as
    source_records. See #9440.
    """

    title: NonEmptyStr
    source_records: NonEmptyList[NonEmptyStr]
    authors: NonEmptyList[Author]
    publishers: NonEmptyList[NonEmptyStr]
    publish_date: NonEmptyStr

    @model_validator(mode="before")
    @classmethod
    def remove_invalid_dates(cls, values):
        """Remove known bad dates prior to validation."""
        is_exempt = any(source_record.split(":")[0] in SUSPECT_DATE_EXEMPT_SOURCES for source_record in values.get("source_records", []))
        if is_exempt:
            return values

        if values.get("publish_date") in SUSPECT_PUBLICATION_DATES:
            values.pop("publish_date")

        return values

    @model_validator(mode="before")
    @classmethod
    def remove_invalid_authors(cls, values):
        """Remove known bad authors (e.g. an author of "N/A") prior to validation."""
        authors = values.get("authors", [])

        # Only examine facially valid records. Other rules will handle validating the schema.
        maybe_valid_authors = [
            author
            for author in authors
            if isinstance(author, dict) and isinstance(author.get("name"), str) and author["name"].lower() not in SUSPECT_AUTHOR_NAMES
        ]
        values["authors"] = maybe_valid_authors

        return values


class FeedSourcedBook(BaseModel):
    """
    A record ingested from a registered provider feed.

    Such feeds (Project Gutenberg, Lenny, ...) are frequently open-access or
    public-domain and lack both an ISBN/LCCN and a publisher, so a complete
    record and a strong identifier are both out of reach. A stable provider
    identifier (``identifiers.project_gutenberg``, ``identifiers.lenny``, ...)
    plus a title and authors is sufficient. Only honored for records whose
    ``source_records`` name a registered feed. See #12844.
    """

    title: NonEmptyStr
    source_records: NonEmptyList[NonEmptyStr]
    authors: NonEmptyList[Author]
    identifiers: dict[str, NonEmptyList[NonEmptyStr]]

    @model_validator(mode="after")
    def at_least_one_identifier(self):
        if not self.identifiers:
            raise ValueError("A feed-sourced record must carry at least one provider identifier")
        return self


class StrongIdentifierBook(BaseModel):
    """
    The model for a book with a title, strong identifier, plus source_records.

    Having one or more strong identifiers is sufficient here. See #9440.
    """

    title: NonEmptyStr
    source_records: NonEmptyList[NonEmptyStr]
    isbn_10: NonEmptyList[NonEmptyStr] | None = None
    isbn_13: NonEmptyList[NonEmptyStr] | None = None
    lccn: NonEmptyList[NonEmptyStr] | None = None

    @model_validator(mode="after")
    def at_least_one_valid_strong_identifier(self):
        if not any([self.isbn_10, self.isbn_13, self.lccn]):
            raise ValueError(f"At least one of the following must be provided: {', '.join(STRONG_IDENTIFIERS)}")

        return self


class import_validator:
    def validate(self, data: dict[str, Any]) -> bool:
        """Validate the given import data.

        Return True if the import object is valid.

        Successful validation of either model is sufficient, though an error
        message will only display for the first model, regardless whether both
        models are invalid. The goal is to encourage complete records.

        This does *not* verify data is sane.
        See https://github.com/internetarchive/openlibrary/issues/9440.
        """
        errors = []

        try:
            CompleteBook.model_validate(data)
            return True
        except ValidationError as e:
            errors.append(e)

        try:
            StrongIdentifierBook.model_validate(data)
            return True
        except ValidationError as e:
            errors.append(e)

        # Records sourced from a *registered* provider feed may validate on a
        # stable provider identifier alone (no ISBN/publisher). To keep the
        # source prefix from being a free pass, the record must ALSO carry an
        # `identifiers` entry keyed by that same registered provider -- i.e. a
        # `project_gutenberg:...` source must present `identifiers.project_gutenberg`.
        # The public import path is unaffected: the source must name a registered
        # feed and the identifiers must corroborate it. #12844
        if feed_providers := self._registered_feed_source_providers(data):
            try:
                book = FeedSourcedBook.model_validate(data)
                if feed_providers & set(book.identifiers):
                    return True
            except ValidationError as e:
                errors.append(e)

        if errors:
            raise errors[0]

        return False

    @staticmethod
    def _registered_feed_source_providers(data: dict[str, Any]) -> set[str]:
        """Registered feed providers named as a ``source_records`` prefix."""
        source_records = data.get("source_records") or []
        providers = import_validator._registered_feed_providers()
        return {record.split(":")[0] for record in source_records if isinstance(record, str) and record.split(":")[0] in providers}

    @staticmethod
    def _registered_feed_providers() -> set[str]:
        """The ``provider_name`` of every registered feed (empty if unavailable).

        ``validate`` runs in contexts with no database configured (unit tests,
        tooling), so a failed registry read must fall back to "no registered
        feeds" — i.e. skip the exemption — rather than break validation. This is
        not the legacy missing-table guard; it keeps validation DB-optional.
        """
        try:
            from openlibrary.bookworm.registry import FeedRegistry

            return FeedRegistry.provider_names()
        except Exception:  # noqa: BLE001 - validation must not require a database
            return set()
