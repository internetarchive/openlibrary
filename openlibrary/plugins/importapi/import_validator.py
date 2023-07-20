from typing import Annotated, Any, TypeVar

from annotated_types import MinLen
from pydantic import BaseModel, ValidationError

T = TypeVar("T")

NonEmptyList = Annotated[list[T], MinLen(1)]
NonEmptyStr = Annotated[str, MinLen(1)]


class Author(BaseModel):
    name: NonEmptyStr


class Book(BaseModel):
    title: NonEmptyStr
    source_records: NonEmptyList[NonEmptyStr]
    authors: NonEmptyList[Author]
    publishers: NonEmptyList[NonEmptyStr]
    publish_date: NonEmptyStr


class import_validator:
    def validate(self, data: dict[str, Any]):
        """Validate the given import data.

        Return True if the import object is valid.
        """

        try:
            Book.model_validate(data)
        except ValidationError as e:
            raise e

        return True
