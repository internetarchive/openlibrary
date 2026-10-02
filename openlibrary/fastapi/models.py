from __future__ import annotations

import json
import re
from typing import Self

from fastapi import HTTPException, Request, Response
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from openlibrary.core.env import get_ol_env

JS_CALLBACK_RE = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$.]*$")


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
    if not v:
        return []
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


def wrap_jsonp(request: Request, data: dict | list | str) -> Response:
    """Wrap data in JSONP callback if callback param is present.

    Always returns a Response object.
    Accepts a dict or list (which will be JSON-serialized), or a pre-serialized JSON string.
    """
    if isinstance(data, str):
        json_string = data
    elif isinstance(data, (dict, list)):
        json_string = json.dumps(data)
    else:
        raise TypeError(f"Unexpected type for JSON response: {type(data)}")

    if callback := request.query_params.get("callback"):
        if not JS_CALLBACK_RE.match(callback):
            raise ValueError("Invalid callback parameter: must be a valid JavaScript identifier (only letters, numbers, underscore, $, and . allowed)")
        return Response(content=f"{callback}({json_string});", media_type="application/javascript")
    return Response(content=json_string, media_type="application/json")


class SolrInternalsParams(BaseModel):
    """
    Internal Solr query parameters for A/B testing search configurations.
    """

    # Dismax parameters
    # See https://solr.apache.org/guide/solr/latest/query-guide/dismax-query-parser.html
    solr_q_op: str | None = Field(
        default=None,
        description="Query operator: default operator between query terms (e.g., AND/OR).",
    )
    solr_qf: str | None = Field(
        default=None,
        description="Query fields: the fields to query un-prefixed parts of the query.",
    )
    solr_mm: str | None = Field(
        default=None,
        description="Minimum match: minimum number/percentage of clauses to match.",
    )
    solr_pf: str | None = Field(default=None, description="Phrase fields: fields to boost phrase matches.")
    solr_ps: str | None = Field(
        default=None,
        description="Phrase slop: allowable distance between terms in a phrase.",
    )
    solr_qs: str | None = Field(default=None, description="Query slop.")
    solr_tie: str | None = Field(
        default=None,
        description="Tie breaker: how to combine scores from multiple fields.",
    )
    solr_bq: str | None = Field(default=None, description="Boost query: additive boost for matching documents.")
    solr_bf: str | None = Field(
        default=None,
        description="Boost functions: additive boost based on function values (e.g., 'min(100,edition_count)').",
    )

    # eDismax parameters
    # See https://solr.apache.org/guide/solr/latest/query-guide/edismax-query-parser.html
    solr_sow: str | None = Field(default=None, description="Split on whitespace: whether to split query terms.")
    solr_mm_autoRelax: str | None = Field(default=None, description="Minimum match auto-relax behavior.")
    solr_boost: str | None = Field(
        default=None,
        description="Boost function: multiplicative boost based on function values.",
    )
    solr_lowercaseOperators: str | None = Field(default=None, description="Whether to treat lowercase 'and'/'or' as operators.")
    solr_pf2: str | None = Field(default=None, description="Phrase fields for bigrams (2-word phrases).")
    solr_ps2: str | None = Field(default=None, description="Phrase slop for bigrams.")
    solr_pf3: str | None = Field(default=None, description="Phrase fields for trigrams (3-word phrases).")
    solr_ps3: str | None = Field(default=None, description="Phrase slop for trigrams.")
    solr_stopwords: str | None = Field(default=None, description="Whether to use stopwords filtering.")

    solr_v: str | None = Field(default=None, description="The value of the edismax query.")

    # More-like-this parameters, used by the `like:` search field.
    # See https://solr.apache.org/guide/solr/latest/query-guide/other-parsers.html#more-like-this-query-parser
    # These descriptions are the help text on /developers/more-like-this, so
    # they are written for a reader tuning the knob, not just naming it.
    mlt_qf: str | None = Field(
        default=None,
        description="Fields whose terms decide whether two works are alike, with boosts (e.g. 'subject^4 title'). Must be stored fields.",
    )
    mlt_mintf: str | None = Field(
        default=None,
        description="Ignore terms appearing fewer than this many times in the seed work. Solr's default of 2 drops nearly everything: a subject is listed once.",
    )
    mlt_mindf: str | None = Field(
        default=None,
        description="Ignore terms appearing in fewer than this many works overall — the knob for discarding typos and one-off cataloguing noise.",
    )
    mlt_maxdf: str | None = Field(
        default=None,
        description="Ignore terms appearing in more than this many works overall — the knob for discarding terms too common to mean anything, like 'Fiction'.",
    )
    mlt_maxqt: str | None = Field(
        default=None,
        description="Cap on how many terms are taken from the seed work. Higher casts a wider net and costs more.",
    )
    mlt_boost: str | None = Field(
        default=None,
        description="'true' weights each extracted term by how distinctive it is; 'false' treats them all as equally meaningful.",
    )

    @staticmethod
    def override(
        base: SolrInternalsParams,
        overrides: SolrInternalsParams | None = None,
    ) -> SolrInternalsParams:
        """
        Overrides a base set of SolrInternalsParams with values from an overrides
        instance.

        You can use the special value "__DELETE__" in the overrides to explicitly set
        a field to None in the combined result.
        """
        if not overrides:
            return base.model_copy()
        combined_data = base.model_dump()
        for field in SolrInternalsParams.model_fields:
            override_value = getattr(overrides, field)

            if override_value == "__DELETE__":
                combined_data[field] = None
            elif override_value is not None:
                combined_data[field] = override_value

        return SolrInternalsParams.model_validate(combined_data)

    def to_solr_edismax_subquery(self, defaults: SolrInternalsParams | None = None) -> str:
        params = []
        # Only the `solr_`-prefixed fields are edismax params; the model also
        # carries `mlt_` ones, which belong to a different query parser.
        for field in SolrInternalsParams.edismax_fields():
            solr_name = field[len("solr_") :].replace("_", ".")
            value = getattr(self, field)
            if defaults and value is None:
                value = getattr(defaults, field)
            if value is None:
                continue

            if value and value.startswith("$"):
                if not re.match(r"^\$[a-zA-Z0-9._-]+$", value):
                    raise ValueError("Invalid solr internal variable supplied")
                # Variables shouldn't be quoted
                params.append(f"{solr_name}={value}")
            else:
                if '"' in value:
                    raise ValueError("Invalid solr internal value supplied")
                params.append(f'{solr_name}="{value}"')
        return "({!edismax " + " ".join(params) + "})" if params else ""

    # Values reach solr inside a `{!mlt ...}` local-params block, so anything
    # that could close or extend that block is refused rather than escaped.
    # Checked here, at the model boundary, so a hand-edited url fails before any
    # query is built.
    @field_validator("mlt_qf", "mlt_mintf", "mlt_mindf", "mlt_maxdf", "mlt_maxqt", "mlt_boost")
    @classmethod
    def _reject_local_param_escapes(cls, value: str | None) -> str | None:
        if value and set(value) & set("\"'{}$"):
            raise ValueError("may not contain quotes, braces or '$'")
        return value

    @staticmethod
    def edismax_fields() -> list[str]:
        return [field for field in SolrInternalsParams.model_fields if field.startswith("solr_")]

    @staticmethod
    def mlt_fields() -> list[str]:
        return [field for field in SolrInternalsParams.model_fields if field.startswith("mlt_")]

    def mlt_overrides(self) -> dict[str, str]:
        """The supplied more-like-this params, keyed by their solr local-param name."""
        return {field[len("mlt_") :]: value for field in SolrInternalsParams.mlt_fields() if (value := getattr(self, field)) is not None}

    @staticmethod
    def from_request(request: Request) -> SolrInternalsParams | None:
        """
        FastAPI dependency that extracts and validates Solr internals params.

        Returns None if the feature is not enabled or no params were provided.
        Raises 403 if params are provided but feature is disabled.
        """
        try:
            params = SolrInternalsParams.model_validate(request.query_params)
        except ValidationError as e:
            error = e.errors()[0]
            raise HTTPException(
                status_code=400,
                detail=f"Invalid solr internals parameter {error['loc'][0]}: {error['msg']}",
            )
        has_params = bool(params.model_dump(exclude_none=True))

        if has_params and not get_ol_env().OL_EXPOSE_SOLR_INTERNALS_PARAMS:
            raise HTTPException(
                status_code=403,
                detail="Solr internals parameters are not allowed in this environment.",
            )

        return params if has_params else None
