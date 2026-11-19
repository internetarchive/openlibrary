"""The merge-request statistics page and its request-independent inputs."""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, ClassVar, Literal
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ValidationInfo, field_validator

from openlibrary.core.edits import STATS_RANGES, STATS_SORT_COLUMNS, CommunityEditsQueue, MergeStatsRow, StatsRole, StatsSort
from openlibrary.core.jinja import render_jinja_template
from openlibrary.core.shell.request import PageMeta
from openlibrary.fastapi.shared.site_page import CurrentUserDep, SitePage, SitePageRoute
from openlibrary.i18n import gettext as _
from openlibrary.utils.async_utils import async_bridge

if TYPE_CHECKING:
    from openlibrary.core.shell.user import ShellUser


class MergeStatsForm(BaseModel):
    group: Literal["reviewers", "submitters"] = "reviewers"
    range: Literal["all", "year", "month"] = "all"
    sort: StatsSort = "total"
    order: Literal["asc", "desc"] = "desc"
    page: int = 1

    GROUPS: ClassVar[dict[str, StatsRole]] = {"reviewers": "reviewer", "submitters": "submitter"}

    @field_validator("group", "range", "sort", "order", mode="before")
    @classmethod
    def valid_choice(cls, value: str, info: ValidationInfo) -> str:
        assert info.field_name is not None
        choices = {"group": cls.GROUPS, "range": STATS_RANGES, "sort": STATS_SORT_COLUMNS, "order": ("asc", "desc")}
        if value not in choices[info.field_name]:
            suffix = 'Must be "asc" or "desc".' if info.field_name == "order" else f"Must be one of {list(choices[info.field_name])}."
            raise HTTPException(400, detail=f'Invalid {info.field_name} parameter: "{value}". {suffix}')
        return value

    @field_validator("page", mode="before")
    @classmethod
    def positive_page(cls, value: str | int) -> int:
        try:
            return max(int(value), 1)
        except ValueError, TypeError:
            raise HTTPException(400, detail=f'Invalid page parameter: "{value}". Must be a number.') from None


@dataclass(frozen=True)
class MergeStatsNav:
    reviewers: str
    submitters: str
    ranges: Mapping[str, str]
    sorts: Mapping[str, str]

    @classmethod
    def from_query(cls, path: str, query: Sequence[tuple[str, str]]) -> MergeStatsNav:
        params: dict[str, list[str]] = {}
        for key, value in query:
            params.setdefault(key, []).append(value)

        def link(**changes: str | None) -> str:
            changed = dict(params)
            for key, value in changes.items():
                if value is None:
                    changed.pop(key, None)
                else:
                    changed[key] = [value]
            encoded = urlencode(changed, doseq=True)
            return path + (f"?{encoded}" if encoded else "")

        selected_query = dict(query)
        order = "asc" if selected_query.get("order", "desc") == "desc" else "desc"
        selected = selected_query.get("sort", "total")
        return cls(
            reviewers=link(group="reviewers", page=None),
            submitters=link(group="submitters", page=None),
            ranges={key: link(range=key, page=None) for key in STATS_RANGES},
            sorts={key: link(sort=key, order=order if key == selected else "desc", page=None) for key in STATS_SORT_COLUMNS},
        )

    @classmethod
    def from_request(cls, request: Request) -> MergeStatsNav:
        return cls.from_query(request.url.path, request.query_params.multi_items())


MergeStatsNavDep = Annotated[MergeStatsNav, Depends(MergeStatsNav.from_request)]


def require_stats_user(request: Request, user: CurrentUserDep) -> ShellUser:
    if user is None:
        path = request.url.path + (f"?{request.url.query}" if request.url.query else "")
        raise HTTPException(303, headers={"Location": "/account/login?" + urlencode({"redirect": path})})
    return user


pages = APIRouter(route_class=SitePageRoute, dependencies=[Depends(require_stats_user)])
PAGE_SIZE = 25


@dataclass(frozen=True)
class MergeStatsData:
    rows: list[MergeStatsRow]
    total_pages: int

    @classmethod
    async def read(cls, form: MergeStatsForm) -> MergeStatsData:
        days = STATS_RANGES[form.range]
        since = dt.date.today() - dt.timedelta(days=days) if days else None
        role = form.GROUPS[form.group]
        rows = await CommunityEditsQueue.get_stats(role, since=since, sort=form.sort, order=form.order, limit=PAGE_SIZE, page=form.page)
        total = await CommunityEditsQueue.get_stats_count(role, since=since)
        return cls(rows=rows, total_pages=(total + PAGE_SIZE - 1) // PAGE_SIZE)

    @classmethod
    def read_sync(cls, form: MergeStatsForm) -> MergeStatsData:
        """Sync bridge for the temporary web.py wrapper."""
        return async_bridge.run(cls.read(form))


@pages.get("/merges/stats")
async def merge_stats(form: Annotated[MergeStatsForm, Query()], nav: MergeStatsNavDep) -> SitePage:
    body = render_jinja_template(
        "merge_request_table/merge_request_stats.html.jinja", form=form, nav=nav, data=await MergeStatsData.read(form), rate_label=_("Merged %")
    )
    return SitePage(body, page=PageMeta(title=_("Community Edit Request Statistics")))
