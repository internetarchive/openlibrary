import json
import re
from typing import Self

from fastapi import Request, Response
from pydantic import BaseModel, Field, model_validator

JS_CALLBACK_RE = re.compile(r"^[A-Za-z0-9_$.]+$")


def parse_comma_separated_list(v: str | list[str]) -> list[str]:
    """
    Parse comma-separated string values into a list of strings.

    This validator handles both string and list inputs, converting:
    - "a,b,c" → ["a", "b", "c"]
    - ["a", "b,c"] → ["a", "b", "c"]

    Used for query parameters that accept comma-separated values like:
    - Search fields: "key,name,author_key"
    - Bibliography keys: "ISBN1,ISBN2,ISBN3"

    Args:
        v: Input value (string or list of strings)

    Returns:
        List of trimmed strings with empty items filtered out
    """
    if isinstance(v, str):
        v = [v]
    return [f.strip() for item in v for f in str(item).split(",") if f.strip()]


class Pagination(BaseModel):
    """Reusable pagination parameters for API endpoints."""

    limit: int = Field(100, ge=0, description="Maximum number of results to return.")
    offset: int | None = Field(None, ge=0, description="Number of results to skip.", exclude=True)
    page: int | None = Field(None, ge=1, description="Page number (1-indexed).")

    @model_validator(mode="after")
    def normalize_pagination(self) -> Self:
        if self.offset is not None:
            self.page = None
        elif self.page is None:
            self.page = 1
        return self


# This is a simple class to have a pagination with a limit of 20. Can be turned into a factory as needed.
class PaginationLimit20(Pagination):
    limit: int = Field(20, ge=0, description="Maximum number of results to return.")


def wrap_jsonp(request: Request, data: dict | str) -> Response:
    """Wrap data in JSONP callback if callback param is present.

    Always returns a Response object.
    Accepts either a dict (which will be JSON-serialized) or a pre-serialized JSON string.
    """
    json_string = json.dumps(data) if isinstance(data, dict) else data
    if callback := request.query_params.get("callback"):
        if not JS_CALLBACK_RE.match(callback):
            raise ValueError("Invalid callback parameter: must be a valid JavaScript identifier (only letters, numbers, underscore, $, and . allowed)")
        return Response(content=f"{callback}({json_string});", media_type="application/javascript")
    return Response(content=json_string, media_type="application/json")
