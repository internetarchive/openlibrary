from __future__ import annotations

import re
from typing import Self

from pydantic import BaseModel, Field, model_validator


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

    @staticmethod
    def combine(
        base: SolrInternalsParams,
        overrides: SolrInternalsParams | None = None,
    ) -> SolrInternalsParams:
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
        for field in SolrInternalsParams.model_fields:
            solr_name = field[len("solr_") :].replace("_", ".")
            value = getattr(self, field)
            if defaults and value is None:
                value = getattr(defaults, field)
            if value is None:
                continue

            if value and value.startswith("$"):
                if not re.match(r"^\$[a-zA-Z0-9.-_]+$", value):
                    raise ValueError("Invalid solr internal variable supplied")
                # Variables shouldn't be quoted
                params.append(f"{solr_name}={value}")
            else:
                if '"' in value:
                    raise ValueError("Invalid solr internal value supplied")
                params.append(f'{solr_name}="{value}"')
        return "({!edismax " + " ".join(params) + "})" if params else ""
