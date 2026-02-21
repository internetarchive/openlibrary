from __future__ import annotations

from typing import Self

from pydantic import BaseModel, Field, model_validator


class Pagination(BaseModel):
    """Reusable pagination parameters for API endpoints."""

    limit: int = Field(100, ge=0, description="Maximum number of results to return.")
    offset: int | None = Field(
        None, ge=0, description="Number of results to skip.", exclude=True
    )
    page: int | None = Field(None, ge=1, description="Page number (1-indexed).")

    @model_validator(mode='after')
    def normalize_pagination(self) -> Self:
        if self.offset is not None:
            self.page = None
        elif self.page is None:
            self.page = 1
        return self


# This is a simple class to have a pagination with a limit of 20. Can be turned into a factory as needed.
class PaginationLimit20(Pagination):
    limit: int = Field(20, ge=0, description="Maximum number of results to return.")
