from typing import Dict, Any


from pydantic import BaseModel, ValidationError, validator


class Author(BaseModel):
    name: str

    @validator("name")
    def author_name_must_not_be_an_empty_string(cls, v):
        if not v:
            raise ValueError("name must not be an empty string")
        return v


class Book(BaseModel):
    title: str
    source_records: list[str]
    authors: list[Author]
    publishers: list[str]
    publish_date: str

    @validator("source_records", "authors", "publishers")
    def list_must_not_be_empty(cls, v):
        if not v:
            raise ValueError("Lists must not be empty")
        return v

    @validator("source_records", "publishers", each_item=True)
    def list_items_must_not_be_empty(cls, v):
        assert v != '', 'Empty strings are not permitted'
        return v

    @validator('title', 'publish_date')
    def strings_must_not_be_empty(cls, v):
        if not len(v):
            raise ValueError("Field must have a non-empty string value")
        return v


class import_validator:
    def validate(self, data: dict[str, Any]):
        """Validates the given import data.

        Returns True if the import object is valid.
        """

        try:
            Book.parse_obj(data)
        except ValidationError as e:
            raise e

        return True
