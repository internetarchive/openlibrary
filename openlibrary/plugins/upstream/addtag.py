"""Handlers for adding and editing tags."""

import web
from markupsafe import Markup, escape

from infogami.core.db import ValidationException
from infogami.infobase.client import ClientException
from infogami.utils import delegate
from infogami.utils.context import context
from infogami.utils.view import add_flash_message, public, safeint
from infogami.utils.view import format as format_text
from openlibrary.accounts import get_current_user
from openlibrary.core.helpers import datestr, parse_datetime, sanitize
from openlibrary.core.jinja import render_jinja_template
from openlibrary.i18n import gettext as _
from openlibrary.plugins.upstream import spamcheck
from openlibrary.plugins.upstream.addbook import safe_seeother, trim_doc
from openlibrary.plugins.upstream.models import Tag
from openlibrary.plugins.upstream.utils import render_template
from openlibrary.utils.request_context import site


@public
def get_tag_types():
    return TAG_TYPES


@public
def get_subject_tag_types():
    return SUBJECT_SUB_TYPES


SUBJECT_SUB_TYPES = [
    "subject",
    "person",
    "place",
    "time",
    "genre",
    "subgenre",
    "content_format",
    "content_warning",
    "literary_form",
    "mood",
    "award",
]
TAG_TYPES = SUBJECT_SUB_TYPES + ["collection"]


def validate_tag(tag):
    return tag.get("name", "") and tag.get("tag_description", "") and tag.get("tag_type", "") in get_tag_types() and tag.get("body") and tag.get("slugs")


def validate_subject_tag(tag):
    return validate_tag(tag) and tag.get("tag_type", "") in get_subject_tag_types()


def parse_slugs(name: str, slugs_input: str) -> list[str]:
    """Build the canonical slugs list for a tag.

    Always includes the slug derived from name. Any additional comma-separated
    slugs from slugs_input are normalized and appended (deduped).
    """
    slugs: list[str] = []
    if name_slug := Tag.normalize(name):
        slugs.append(name_slug)
    for raw in slugs_input.split(","):
        s = Tag.normalize(raw)
        if s and s not in slugs:
            slugs.append(s)
    return slugs


def create_tag(tag: dict):
    d = {"type": {"key": "/type/tag"}, **tag}
    if not validate_tag(d):
        raise ValueError("Invalid data for tag creation")
    tag = Tag.create(trim_doc(d))
    return tag


def create_subject_tag(tag: dict):
    d = {"type": {"key": "/type/tag"}, **tag}
    if not validate_subject_tag(d):
        raise ValueError("Invalid data for subject tag creation")
    tag = Tag.create(trim_doc(d))
    return tag


def find_match(name_or_slug: str, tag_type: str) -> str:
    """Returns the key of an existing tag matching name_or_slug and type, or ''.

    Accepts either a human-readable name or a slug; Tag.find() normalizes both.
    """
    matches = Tag.find(name_or_slug, tag_type=tag_type)
    return matches[0] if matches else ""


def can_create_tag(user) -> bool:
    """Whether the given user can create a new tag."""
    return bool(user and (user.is_admin() or user.is_curator()))


def derive_subject_key(tag) -> str:
    """The subject page the tag maps to."""
    key = "/subjects/"
    if tag.tag_type != "subject":
        key += f"{tag.tag_type}:"
    return (key + tag.name.replace(" ", "_")).lower()


def render_tags_index(*, tags, page: int, has_next: bool, tag_type: str | None) -> str:
    """The body of /tags, rendered by both servers."""
    return render_jinja_template(
        "type/tag/index.html.jinja",
        tags=tags,
        page=page,
        has_next=has_next,
        tag_type=tag_type,
        tag_types=TAG_TYPES,
        subject_tag_types=SUBJECT_SUB_TYPES,
    )


def render_tag_view(tag) -> str:
    """The body of a tag's page, rendered by both servers."""
    author = tag.get_most_recent_change().author
    is_subject_tag = tag.tag_type in SUBJECT_SUB_TYPES
    return render_jinja_template(
        "type/tag/view.html.jinja",
        tag=tag,
        title=tag.name,
        description_html=Markup(sanitize(format_text(tag.get("tag_description") or ""))),
        body_html=Markup(sanitize(format_text(tag.get("body") or ""))),
        subject_key=derive_subject_key(tag) if is_subject_tag else None,
        is_subject_tag=is_subject_tag,
        edit_url=tag.key + "?m=edit",
        history_url=tag.url(m="history"),
        show_edit=not tag.is_fake_record(),
        date=datestr(parse_datetime(last_modified)) if (last_modified := tag.get("last_modified")) else "",
        author_link=author.render_link() if author else None,
    )


def render_tag_form(
    *,
    name: str = "",
    slugs: str = "",
    tag_description: str = "",
    body: str = "",
    tag_type: str = "",
    deputy: str = "",
    is_editing: bool = False,
    key: str = "",
    redirect: str | None = None,
    can_delete: bool = False,
    comment: str | None = None,
) -> str:
    """The body of /tag/add and /tags/OLnT/edit, rendered by both servers."""
    return render_jinja_template(
        "type/tag/form.html.jinja",
        name=name,
        slugs=slugs,
        tag_description=tag_description,
        body=body,
        tag_type=tag_type,
        deputy=deputy,
        is_editing=is_editing,
        key=key,
        redirect=redirect,
        can_delete=can_delete,
        comment=comment,
        tag_types=TAG_TYPES,
    )


def _render_tag_form(i, *, is_editing: bool = False, key: str = "", redirect: str | None = None, can_delete: bool = False, comment: str | None = None):
    """Render the tag form for a web.py handler, whose layout reads the title off the result."""
    slugs = i.get("slugs") or ""
    if isinstance(slugs, (list, tuple)):
        slugs = ", ".join(slugs)
    body = render_tag_form(
        name=i.get("name") or "",
        slugs=slugs,
        tag_description=i.get("tag_description") or "",
        body=i.get("body") or "",
        tag_type=i.get("tag_type") or "",
        deputy=i.get("deputy") or "",
        is_editing=is_editing,
        key=key,
        redirect=redirect,
        can_delete=can_delete,
        comment=comment,
    )
    context["robots"] = "noindex,nofollow"
    title = _("Edit tag") if is_editing else _("Add a tag")
    return web.template.TemplateResult(__body__=body, title=escape(title))


class addtag(delegate.page):
    path = "/tag/add"

    def GET(self):
        """Main user interface for adding a tag to Open Library."""
        if not (patron := get_current_user()):
            # NOTE : will lose any query params on login redirect
            raise web.seeother(f"/account/login?redirect={self.path}")

        if not self.has_permission(patron):
            raise web.unauthorized(message="Permission denied to add tags")

        i = web.input(name=None)

        return _render_tag_form(i)

    def has_permission(self, user) -> bool:
        """
        Returns True if the given user can create a new Tag
        """
        return can_create_tag(user)

    def POST(self):
        i = web.input(
            name="",
            tag_type="",
            tag_description="",
            body="",
            slugs="",
        )

        if spamcheck.is_spam(i, allow_privileged_edits=True):
            return render_template("message.html", "Oops", "Something went wrong. Please try again later.")

        if not (patron := get_current_user()):
            raise web.seeother(f"/account/login?redirect={self.path}")

        if not self.has_permission(patron):
            raise web.unauthorized(message="Permission denied to add tags")

        i["slugs"] = parse_slugs(i.name, i.slugs)
        if not self.validate_input(i):
            raise web.badrequest()

        for slug in i["slugs"]:
            if match := find_match(slug, i.tag_type):
                add_flash_message(
                    "error",
                    f'A tag with slug "{slug}" and the same type already exists: <a href="{match}">{match}</a>',
                )
                return _render_tag_form(i)

        tag = create_tag(i)
        raise safe_seeother(tag.key)

    def validate_input(self, i):
        if i.tag_type in get_subject_tag_types():
            return validate_subject_tag(i)
        return validate_tag(i)


class tag_edit(delegate.page):
    path = r"(/tags/OL\d+T)/edit"

    def GET(self, key):
        tag = site.get().get(key)
        if tag is None:
            raise web.notfound()

        if not self.has_permission(tag):
            return render_template(
                "permission_denied",
                web.ctx.fullpath,
                "Permission denied to edit " + key + ".",
            )

        i = web.input(redir=None)
        user = get_current_user()
        return _render_tag_form(
            tag,
            is_editing=True,
            key=tag.key,
            redirect=i.redir,
            can_delete=bool(user and user.is_super_librarian_or_higher()),
            comment=getattr(tag, "comment_", None),
        )

    def POST(self, key):
        tag = site.get().get(key)
        if tag is None:
            raise web.notfound()

        if not self.has_permission(tag):
            return render_template(
                "permission_denied",
                web.ctx.fullpath,
                "Permission denied to edit " + key + ".",
            )

        i = web.input(_comment=None, redir=None)
        if "_delete" in i:
            try:
                tag = site.get().new(key, {"key": key, "type": {"key": "/type/delete"}})
                tag._save(comment=i._comment, action="delete-tag")
                raise safe_seeother(key)
            except (ClientException, ValidationException) as e:
                add_flash_message("error", str(e))
                return _render_tag_form(tag, is_editing=True, key=key, redirect=i.redir)

        formdata = trim_doc(i)
        if formdata:
            slugs_input = formdata.get("slugs", "") or ""
            formdata["slugs"] = parse_slugs(formdata.get("name", ""), slugs_input)
        if not formdata or not self.validate(formdata, formdata.tag_type):
            raise web.badrequest()
        if tag.tag_type != formdata.tag_type:
            for slug in formdata["slugs"]:
                if match := find_match(slug, formdata.tag_type):
                    add_flash_message(
                        "error",
                        f'A tag with slug "{slug}" and the same type already exists: <a href="{match}">{match}</a>',
                    )
                    return _render_tag_form(formdata, is_editing=True, key=key, redirect=i.redir)

        try:
            tag.update(formdata)
            tag._save(comment=i._comment, action="edit-tag")
            raise safe_seeother(i.redir or key)
        except (ClientException, ValidationException) as e:
            add_flash_message("error", str(e))
            return _render_tag_form(tag, is_editing=True, key=key, redirect=i.redir)

    def validate(self, data, tag_type):
        if tag_type in SUBJECT_SUB_TYPES:
            return validate_subject_tag(data)
        else:
            return validate_tag(data)

    def has_permission(self, tag):
        """
        Returns `True` if the current user is permitted to edit a tag.

        :param tag: A Tag object
        :return: True if current user can edit a tag, False otherwise
        """
        if not site.get().can_write(tag.key):
            return False
        if not (patron := get_current_user()):
            return False

        is_in_permitted_group = patron.is_admin() or patron.is_curator()
        is_deputy = patron.key == tag.get("deputy", None)

        if is_in_permitted_group:
            return True

        return tag.tag_type in SUBJECT_SUB_TYPES and is_deputy


class tag_search(delegate.page):
    path = "/tags/-/([^/]+):([^/]+)"

    def GET(self, type, name):
        matches = Tag.find(name, tag_type=type)
        if matches:
            return web.seeother(matches[0])
        return render_template("notfound", f"/tags/-/{type}:{name}", create=False)


class tag_view(delegate.page):
    path = r"(/tags/OL\d+T)"

    def GET(self, key):
        tag = site.get().get(key)
        if tag is None or tag.type.key != "/type/tag":
            return render_template("notfound", key)
        return web.template.TemplateResult(__body__=render_tag_view(tag), title=escape(tag.name))


class tags_index(delegate.page):
    path = "/tags"

    def GET(self):
        i = web.input(page=1, type=None)
        page_num = max(1, safeint(i.page, 1))
        limit = 20
        offset = (page_num - 1) * limit
        tag_type = i.type if i.type in TAG_TYPES else None

        q = {"type": "/type/tag", "limit": limit + 1, "offset": offset}
        if tag_type:
            q["tag_type"] = tag_type

        tag_keys = site.get().things(q)
        has_next = len(tag_keys) > limit
        tags = site.get().get_many(tag_keys[:limit]) if tag_keys else []

        body = render_tags_index(tags=tags, page=page_num, has_next=has_next, tag_type=tag_type)
        # web.py's layout reads the title off the result, already escaped, as from Templetor's $var.
        return web.template.TemplateResult(__body__=body, title=escape(_("Tags")))


def setup():
    """Do required setup."""
    pass
