"""What the /tasks pages fetch after load (the "happening now" feed and the dashboard's list, both polled by contribute.js),
and the /tasks/admin pages, where the community projects are run."""

from __future__ import annotations

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from openlibrary.contribute import feed, initiatives, manage
from openlibrary.core.jinja import render_jinja_template
from openlibrary.core.shell.request import PageMeta
from openlibrary.core.shell.user import ShellUser
from openlibrary.fastapi.auth import AuthenticatedUser, require_authenticated_user
from openlibrary.fastapi.shared.site_page import CurrentUserDep, SitePage, SitePageRoute
from openlibrary.i18n import gettext as _
from openlibrary.plugins.openlibrary import contribute

router = APIRouter()


def require_project_manager(request: Request, user: CurrentUserDep) -> ShellUser:
    """Whoever may run the community projects: super-librarians and admins, as `User.can_manage_tasks` has it.

    A visitor is sent to log in and back; a member without the role gets a 403.
    """
    if user is None:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": f"/account/login?redirect={quote(request.url.path)}"})
    if not user.is_super_librarian:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only super-librarians and admins can manage community projects")
    return user


ProjectManagerDep = Annotated[ShellUser, Depends(require_project_manager)]

# On the router, so a page added here can't be left ungated.
pages = APIRouter(route_class=SitePageRoute, dependencies=[Depends(require_project_manager)])


def admin_page(title: str) -> PageMeta:
    """The shell values every /tasks/admin page shares: the Tasks stylesheet, and kept out of search engines."""
    return PageMeta(title=title, cssfile="contribute", bodyclass=("contribute-body",), robots="noindex")


class FeedRow(BaseModel):
    id: str
    key: str
    title: str
    authors: str
    cover_url: str
    kind: str
    action: str
    editor: str
    editor_key: str
    comment: str
    timestamp: str


class FeedResponse(BaseModel):
    rows: list[FeedRow]


# Plain def: the memcache read is blocking I/O, so it runs in the threadpool rather than on the event loop.
@router.get("/tasks/feed.json", response_model=FeedResponse)
def tasks_feed(
    limit: Annotated[int, Query(gt=0, le=50)] = 20,
    offset: Annotated[int, Query(ge=0, description="Where in the rotation to start.")] = 0,
) -> FeedResponse:
    """Recent human edits to catalog records as rows for the Tasks page feed, rotated and restamped back from now."""
    rows = feed.recent_rows(limit, offset)
    return FeedResponse(rows=[FeedRow(**r) for r in rows])


# Plain def: the memcache read and the edition loads are blocking I/O, so they run in the threadpool.
@router.get("/tasks/rows", response_class=HTMLResponse, include_in_schema=False)
def tasks_rows(
    _user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
    task: Annotated[str, Query(description="The dashboard filter; unknown values mean all tasks.")] = "",
    initiative: Annotated[str, Query(description="The initiative's slug; unknown values mean the headline one.")] = "",
) -> Response:
    """The dashboard's list on its own, for a page that rendered placeholders: 202 while the pool is still being built."""
    if (rows := contribute.build_task_rows(contribute.normalize_filter(task), contribute.get_initiative(initiative))) is None:
        return Response(status_code=202)
    return HTMLResponse(render_jinja_template("contribute/rows.html.jinja", rows=rows))


# Plain defs: the gaps come from memcache and the counts from the store, both blocking.
@pages.get("/tasks/admin")
def tasks_admin() -> SitePage:
    """Every community project, whatever its status, with how far along it is."""
    body = render_jinja_template("contribute/admin/index.html.jinja", page=manage.build_index())
    return SitePage(body, page=admin_page(_("Community projects")))


@pages.get("/tasks/admin/{slug}")
def tasks_admin_project(slug: str) -> SitePage:
    """One community project: its definition, its progress by detail, and its saves."""
    if not (initiative := next((i for i in initiatives.every() if i.slug == slug), None)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such project")
    detail = manage.build_detail(initiative)
    body = render_jinja_template("contribute/admin/project.html.jinja", page=detail)
    return SitePage(body, page=admin_page(detail["project"]["title"]))
