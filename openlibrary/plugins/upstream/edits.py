"""Librarian Edits"""

import datetime
import json
from typing import ClassVar, Literal

import web

from infogami.infobase.client import ClientException
from infogami.utils import delegate
from infogami.utils.view import render_template, require_login
from openlibrary import accounts
from openlibrary.core.edits import (
    STATS_RANGES,
    STATS_SORT_COLUMNS,
    ApiMode,
    CommunityEditsQueue,
    get_status_for_view,
)
from openlibrary.utils.request_context import site
from openlibrary.utils.retry import RetryStrategy

# Usergroups that may use create or update merge requests
ALLOWED_USERGROUPS: list[str] = [
    "/usergroup/librarians",
    "/usergroup/super-librarians",
    "/usergroup/admin",
]


def response(status="ok", **kwargs):
    return {"status": status, **kwargs}


def process_merge_request(rtype, data):
    user = accounts.get_current_user()
    username = user["key"].split("/")[-1]
    # Request types can be: create-request, update-request
    if rtype == "create-request":
        resp = community_edits_queue.create_request(username, **data)
    elif rtype == "update-request":
        resp = community_edits_queue.update_request(username, **data)
    else:
        resp = response(status="error", error="Unknown request type")
    return resp


def perform_merge_update(mrid: str | None, olids: str, comment: str | None) -> None:
    """Orchestrate the merge request update with retries.

    Builds the appropriate request type and data, then attempts to process
    the merge request with retry logic.

    Args:
        mrid: Merge request ID to approve, or None to create a new request.
        olids: Comma-separated author keys (used when creating a new request).
        comment: Optional comment for the merge request.

    Raises:
        MaxRetriesExceeded: If all retry attempts to process the request fail.
    """

    def update_request() -> None:
        if mrid:
            process_merge_request(
                "update-request",
                {
                    "action": "approve",
                    "mrid": mrid,
                    **({"comment": comment} if comment else {}),
                },
            )
        else:
            process_merge_request(
                "create-request",
                {
                    "mr_type": 2,
                    "olids": olids,
                    "action": "create-merged",
                    **({"comment": comment} if comment else {}),
                },
            )

    RetryStrategy([ClientException], max_retries=5, delay=2)(update_request)


class community_edits_queue_stats(delegate.page):
    path = "/merges/stats"

    STATS_PAGE_SIZE = 25
    GROUPS: ClassVar[dict[str, str]] = {"reviewers": "reviewer", "submitters": "submitter"}

    @require_login
    def GET(self) -> str | web.HTTPError:
        i = web.input(group="reviewers", range="all", sort="total", order="desc", page=1)

        if i.group not in self.GROUPS:
            return web.badrequest(f'Invalid group parameter: "{i.group}". Must be one of {list(self.GROUPS)}.')
        if i.range not in STATS_RANGES:
            return web.badrequest(f'Invalid range parameter: "{i.range}". Must be one of {list(STATS_RANGES)}.')
        if i.sort not in STATS_SORT_COLUMNS:
            return web.badrequest(f'Invalid sort parameter: "{i.sort}". Must be one of {list(STATS_SORT_COLUMNS)}.')
        if i.order not in ("asc", "desc"):
            return web.badrequest(f'Invalid order parameter: "{i.order}". Must be "asc" or "desc".')
        try:
            page = max(int(i.page), 1)
        except ValueError:
            return web.badrequest(f'Invalid page parameter: "{i.page}". Must be a number.')

        days = STATS_RANGES[i.range]
        since = datetime.date.today() - datetime.timedelta(days=days) if days else None
        role = self.GROUPS[i.group]

        rows = CommunityEditsQueue.get_stats(
            role,
            since=since,
            sort=i.sort,
            order=i.order,
            limit=self.STATS_PAGE_SIZE,
            page=page,
        )
        total = CommunityEditsQueue.get_stats_count(role, since=since)

        return render_template(
            "merge_request_table/merge_request_stats",
            rows,
            total,
            group=i.group,
            page=page,
            page_size=self.STATS_PAGE_SIZE,
        )


class community_edits_queue(delegate.page):
    path = "/merges"

    @require_login
    def GET(self) -> str | web.HTTPError:
        i = web.input(
            page=1,
            limit=25,
            mode="open",
            submitter=None,
            reviewer=None,
            order="desc",
            status=None,
        )

        order: Literal["asc", "desc"] = "desc"
        if i.order and i.order.lower() in ("asc", "desc"):
            order = i.order.lower()
        else:
            return web.badrequest(f'Invalid order parameter: "{i.order}". Must be "asc" or "desc".')

        mode: ApiMode = "open"
        if i.mode and i.mode.lower() in CommunityEditsQueue.MODES:
            mode = i.mode.lower()
        else:
            return web.badrequest(f'Invalid mode parameter: "{i.mode}". Must be one of {list(CommunityEditsQueue.MODES.keys())}.')

        merge_requests = CommunityEditsQueue.get_requests(
            page=int(i.page),
            limit=int(i.limit),
            mode=mode,
            submitter=i.submitter,
            reviewer=i.reviewer,
            order_by_updated=order,
            status=i.status,
        ).list()

        total_found = {
            "open": CommunityEditsQueue.get_counts_by_mode(mode="open", submitter=i.submitter, reviewer=i.reviewer),
            "closed": CommunityEditsQueue.get_counts_by_mode(mode="closed", submitter=i.submitter, reviewer=i.reviewer),
            "submitters": CommunityEditsQueue.get_submitters(),
            "reviewers": CommunityEditsQueue.get_reviewers(),
        }

        librarians = {
            "submitters": CommunityEditsQueue.get_submitters(),
            "reviewers": CommunityEditsQueue.get_reviewers(),
        }

        return render_template(
            "merge_request_table/merge_request_table",
            total_found,
            librarians,
            merge_requests=merge_requests,
        )

    @require_login
    def POST(self):
        if not (user := accounts.get_current_user()) or not user.is_member_of_any(ALLOWED_USERGROUPS):
            raise web.unauthorized()

        data = json.loads(web.data())
        resp = process_merge_request(data.pop("rtype", ""), data)

        return delegate.RawText(json.dumps(resp), content_type="application/json")

    @staticmethod
    def create_request(
        username,
        action="",
        mr_type=None,
        olids="",
        comment: str | None = None,
        primary: str | None = None,
    ):
        def is_valid_action(action):
            return action in ("create-pending", "create-merged")

        def needs_unique_url(mr_type):
            return mr_type in (
                CommunityEditsQueue.TYPE["WORK_MERGE"],
                CommunityEditsQueue.TYPE["AUTHOR_MERGE"],
            )

        if is_valid_action(action):
            olid_list = olids.split(",")

            title = community_edits_queue.create_title(mr_type, olid_list)
            url = community_edits_queue.create_url(mr_type, olid_list, primary=primary)

            # Validate URL
            is_valid_url = True
            if needs_unique_url(mr_type) and CommunityEditsQueue.exists(url):
                is_valid_url = False

            if is_valid_url:
                if action == "create-pending":
                    result = CommunityEditsQueue.submit_request(url, username, title=title, comment=comment, mr_type=mr_type)
                elif action == "create-merged":
                    result = CommunityEditsQueue.submit_request(
                        url,
                        username,
                        title=title,
                        comment=comment,
                        reviewer=username,
                        status=CommunityEditsQueue.STATUS["MERGED"],
                        mr_type=mr_type,
                    )
                resp = response(id=result) if result else response(status="error", error="Request creation failed.")
            else:
                resp = response(
                    status="error",
                    error="A merge request for these items already exists.",
                )
        else:
            resp = response(
                status="error",
                error=f'Action "{action}" is invalid for this request type.',
            )

        return resp

    @staticmethod
    def update_request(username, action="", mrid=None, comment=None):
        # Comment on existing request:
        if action == "comment":
            if comment:
                CommunityEditsQueue.comment_request(mrid, username, comment)
                resp = response()
            else:
                resp = response(status="error", error="No comment sent in request.")
        # Assign to existing request:
        elif action == "claim":
            result = CommunityEditsQueue.assign_request(mrid, username)
            resp = response(**result)
        # Unassign from existing request:
        elif action == "unassign":
            CommunityEditsQueue.unassign_request(mrid)
            status = get_status_for_view(CommunityEditsQueue.STATUS["PENDING"])
            resp = response(newStatus=status)
        # Close request by approving:
        elif action == "approve":
            CommunityEditsQueue.update_request_status(mrid, CommunityEditsQueue.STATUS["MERGED"], username, comment=comment)
            resp = response()
        # Close request by declining:
        elif action == "decline":
            CommunityEditsQueue.update_request_status(mrid, CommunityEditsQueue.STATUS["DECLINED"], username, comment=comment)
            resp = response()
        # Unknown request:
        else:
            resp = response(
                status="error",
                error=f'Action "{action}" is invalid for this request type.',
            )

        return resp

    @staticmethod
    def create_url(mr_type: int, olids: list[str], primary: str | None = None) -> str:
        if mr_type == CommunityEditsQueue.TYPE["WORK_MERGE"]:
            primary_param = f"&primary={primary}" if primary else ""
            return f"/works/merge?records={','.join(olids)}{primary_param}"
        elif mr_type == CommunityEditsQueue.TYPE["AUTHOR_MERGE"]:
            return f"/authors/merge?records={','.join(olids)}"
        return ""

    @staticmethod
    def create_title(mr_type: int, olids: list[str]) -> str:
        if mr_type == CommunityEditsQueue.TYPE["WORK_MERGE"]:
            for olid in olids:
                book = site.get().get(f"/works/{olid}")
                if book and book.title:
                    return book.title
        elif mr_type == CommunityEditsQueue.TYPE["AUTHOR_MERGE"]:
            for olid in olids:
                author = site.get().get(f"/authors/{olid}")
                if author and author.name:
                    return author.name
        return "Unknown record"


def setup():
    pass
