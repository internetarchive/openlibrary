"""What the /tasks pages fetch after load (the "happening now" feed, and the dashboard's rows that <ol-task-rows> polls for),
and the /tasks/admin pages, where the community projects are run."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from openlibrary.contribute import feed, initiatives, manage
from openlibrary.contribute.rows import TaskRowsResponse
from openlibrary.core.jinja import render_jinja_template
from openlibrary.core.shell.request import PageMeta
from openlibrary.core.shell.user import ShellUser
from openlibrary.fastapi.auth import AuthenticatedUser, require_authenticated_user
from openlibrary.fastapi.shared.site_page import CurrentUserDep, SitePage, SitePageRoute
from openlibrary.fastapi.shared.utils import FlashType, set_flash_cookie
from openlibrary.i18n import gettext as _
from openlibrary.plugins.openlibrary import contribute
from openlibrary.utils.request_context import site

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
# The pages anyone may read, visitors included.
public_pages = APIRouter(route_class=SitePageRoute)


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
@router.get("/tasks/rows.json", response_model=TaskRowsResponse, include_in_schema=False)
def tasks_rows(
    _user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
    task: Annotated[str, Query(description="The dashboard filter; unknown values mean all tasks.")] = "",
    initiative: Annotated[str, Query(description="The initiative's slug; unknown values mean the headline one.")] = "",
) -> TaskRowsResponse | Response:
    """The dashboard's rows for <ol-task-rows>: 202 with no body while the pool is still being built.

    Internal: the shape follows the component and can change without notice.
    """
    if (rows := contribute.build_task_rows(contribute.normalize_filter(task), contribute.get_initiative(initiative))) is None:
        return Response(status_code=202)
    return TaskRowsResponse(rows=rows)


def find_project(slug: str) -> initiatives.Initiative:
    """Any project by its slug, whatever its status. Read fresh: a page loaded right after a change must show it."""
    if not (initiative := next((i for i in initiatives.every(initiatives.read_definitions(site.get())) if i.slug == slug), None)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such project")
    return initiative


def back_to_project(slug: str, kind: FlashType, message: str) -> RedirectResponse:
    """Back to the project's page after a change, with what happened as a banner."""
    response = RedirectResponse(f"{manage.BASE_URL}/{slug}", status_code=status.HTTP_303_SEE_OTHER)
    set_flash_cookie(response, kind, message)
    return response


def change_project(slug: str, user: ShellUser, rev: str, action: str, changes: dict, done: str) -> RedirectResponse:
    try:
        if action == "headline":
            initiatives.set_headline(site.get(), slug, user.key, rev)
        else:
            initiatives.change(site.get(), slug, changes, user.key, action, rev)
    except initiatives.Conflict:
        return back_to_project(slug, "error", _("Someone else changed this project while you had it open. Check it below, then try again."))
    return back_to_project(slug, "note", done)


@public_pages.get("/tasks/faq")
async def tasks_faq() -> SitePage:
    """Answers for the people doing tasks: what an answer covers, skipping versus "I couldn't find it", and how projects work."""
    body = render_jinja_template("contribute/faq.html.jinja")
    return SitePage(body, page=PageMeta(title=_("Tasks FAQ"), cssfile="contribute", bodyclass=("contribute-body",)))


# Plain defs: the gaps come from memcache and the counts from the store, both blocking.
@pages.get("/tasks/admin")
def tasks_admin() -> SitePage:
    """Every community project, whatever its status, with how far along it is."""
    body = render_jinja_template("contribute/admin/index.html.jinja", page=manage.build_index())
    return SitePage(body, page=admin_page(_("Community projects")))


class NewProject(BaseModel):
    """The create form. Every field is text, so a bad value comes back as a message on the form, not a 422."""

    title: str = ""
    description: str = ""
    fields: list[str] = []
    source: str = ""
    books: str = ""
    list_url: str = ""
    size: str = ""
    starts: str = ""
    ends: str = ""
    goal: str = ""


def new_project_page(form: dict, status_code: int = status.HTTP_200_OK) -> SitePage:
    body = render_jinja_template("contribute/admin/new.html.jinja", page=form)
    return SitePage(body, page=admin_page(_("New project")), status_code=status_code)


# Declared before the {slug} routes, which would otherwise take "new" for a project.
@pages.get("/tasks/admin/new")
def tasks_admin_new() -> SitePage:
    return new_project_page(manage.build_new_form())


@pages.post("/tasks/admin/new")
def tasks_admin_create(form: Annotated[NewProject, Form()], user: ProjectManagerDep) -> Response:
    """Set up a project. A list someone named is read and frozen here; a picker's is picked afterwards, off the request."""
    values = form.model_dump()
    definition, resolved, error = manage.parse_create(values)
    if error:
        # Shown on the form as it was posted: a pasted list is too much to lose to a redirect.
        return new_project_page(manage.build_new_form(values, error), status.HTTP_400_BAD_REQUEST)
    initiative = initiatives.create(site.get(), definition, resolved.picks if resolved else None, user.key)
    return back_to_project(initiative.slug, "note", _("The project is set up. Check its books below."))


@pages.get("/tasks/admin/{slug}")
def tasks_admin_project(slug: str) -> SitePage:
    """One community project: its definition, its progress by detail, and its saves."""
    detail = manage.build_detail(find_project(slug))
    body = render_jinja_template("contribute/admin/project.html.jinja", page=detail)
    return SitePage(body, page=admin_page(detail["project"]["title"]))


Rev = Annotated[str, Form(description="The definition's revision when the page was rendered; a stale one is refused.")]


@pages.post("/tasks/admin/{slug}/hide")
def tasks_admin_hide(slug: str, user: ProjectManagerDep, rev: Rev = "") -> RedirectResponse:
    find_project(slug)
    return change_project(slug, user, rev, "hide", {"hidden": True}, _("The project is hidden from the Tasks and stats pages."))


@pages.post("/tasks/admin/{slug}/unhide")
def tasks_admin_unhide(slug: str, user: ProjectManagerDep, rev: Rev = "") -> RedirectResponse:
    find_project(slug)
    return change_project(slug, user, rev, "unhide", {"hidden": False}, _("The project is visible again."))


@pages.post("/tasks/admin/{slug}/stop")
def tasks_admin_stop(slug: str, user: ProjectManagerDep, rev: Rev = "") -> RedirectResponse:
    if find_project(slug).status() != "live":
        return back_to_project(slug, "error", _("Only a live project can be stopped."))
    ends_at = datetime.now(UTC).isoformat(timespec="seconds")
    return change_project(slug, user, rev, "stop", {"ends_at": ends_at}, _("The project has ended. It hands out no more tasks."))


@pages.post("/tasks/admin/{slug}/headline")
def tasks_admin_headline(slug: str, user: ProjectManagerDep, rev: Rev = "") -> RedirectResponse:
    initiative = find_project(slug)
    if initiative.status() != "live" or initiative.hidden:
        return back_to_project(slug, "error", _("Only a live project that isn't hidden can be featured."))
    return change_project(slug, user, rev, "headline", {}, _("This is now the featured project."))


@pages.post("/tasks/admin/{slug}/edit")
def tasks_admin_edit(
    slug: str,
    user: ProjectManagerDep,
    rev: Rev = "",
    title: Annotated[str, Form()] = "",
    description: Annotated[str, Form()] = "",
    starts: Annotated[str, Form()] = "",
    ends: Annotated[str, Form()] = "",
    goal: Annotated[str, Form()] = "",
) -> RedirectResponse:
    initiative = find_project(slug)
    changes, error = manage.parse_edit(initiative, title, description, starts, ends, goal)
    if not error and changes.get("starts_at") and not initiative.pick and not initiatives.load_frozen(initiative, site.get()):
        error = _("A project needs books before it can start.")
    if error:
        return back_to_project(slug, "error", error)
    if not changes:
        return back_to_project(slug, "note", _("Nothing changed."))
    return change_project(slug, user, rev, "edit", changes, _("Saved."))


@pages.post("/tasks/admin/{slug}/delete")
def tasks_admin_delete(slug: str, user: ProjectManagerDep) -> RedirectResponse:
    initiative = find_project(slug)
    if initiatives.is_builtin(initiative) or initiative.status() not in ("draft", "scheduled"):
        return back_to_project(slug, "error", _("Only a project that hasn't started can be deleted. Stop or hide this one."))
    initiatives.delete(site.get(), initiative)
    response = RedirectResponse(manage.BASE_URL, status_code=status.HTTP_303_SEE_OTHER)
    set_flash_cookie(response, "note", _("The project is deleted."))
    return response
