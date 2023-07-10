from typing import Any


from pydantic import field_validator, BaseModel, ValidationError, validator


class Author(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def author_name_must_not_be_an_empty_string(cls, v):
        if v:
            return v
        raise ValueError("name must not be an empty string")


class Book(BaseModel):
    title: str
    source_records: list[str]
    authors: list[Author]
    publishers: list[str]
    publish_date: str

    @field_validator("source_records", "authors", "publishers")
    @classmethod
    def list_must_not_be_empty(cls, v):
        if v:
            return v
        raise ValueError("Lists must not be empty")

    # TODO[pydantic]: We couldn't refactor the `validator`, please replace it by `field_validator` manually.
    # Check https://docs.pydantic.dev/dev-v2/migration/#changes-to-validators for more information.
    @validator("source_records", "publishers", each_item=True)
    def list_items_must_not_be_empty(cls, v):
        if v:
            return v
        raise ValueError("Empty strings are not permitted")

    @field_validator('title', 'publish_date')
    @classmethod
    def strings_must_not_be_empty(cls, v):
        if v:
            return v
        raise ValueError("Field must have a non-empty string value")


class import_validator:
    def validate(self, data: dict[str, Any]):
        """Validate the given import data.

        Return True if the import object is valid.
        """

        try:
            Book.parse_obj(data)
        except ValidationError as e:
            raise e

        return True
