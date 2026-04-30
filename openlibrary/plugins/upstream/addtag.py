"""Handlers for adding and editing tags."""

import web
from infogami.core.db import ValidationException
from infogami.infobase.client import ClientException
from infogami.utils import delegate
from infogami.utils.view import add_flash_message, public, safeint

from openlibrary.accounts import get_current_user
from openlibrary.plugins.upstream import spamcheck
from openlibrary.plugins.upstream.addbook import safe_seeother, trim_doc
from openlibrary.plugins.upstream.models import Tag
from openlibrary.plugins.upstream.utils import render_template


@public
def get_tag_types():
    return TAG_TYPES


@public
def get_subject_tag_types():
    return SUBJECT_SUB_TYPES


SUBJECT_SUB_TYPES = ["subject", "person", "place", "time"]
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


class addtag(delegate.page):
    path = "/tag/add"

    def GET(self):
        """Main user interface for adding a tag to Open Library."""
        if not (patron := get_current_user()):
            # NOTE : will lose any query params on login redirect
            raise web.seeother(f"/account/login?redirect={self.path}")

        if not self.has_permission(patron):
            raise web.unauthorized(message="Permission denied to add tags")

        i = web.input(name=None, type=None, sub_type=None)

        return render_template("type/tag/form", i)

    def has_permission(self, user) -> bool:
        """
        Returns True if the given user can create a new Tag
        """
        return user and (user.is_admin() or user.is_curator())

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
                return render_template("type/tag/form", i)

        tag = create_tag(i)
        raise safe_seeother(tag.key)

    def validate_input(self, i):
        if i.tag_type in get_subject_tag_types():
            return validate_subject_tag(i)
        return validate_tag(i)


class tag_edit(delegate.page):
    path = r"(/tags/OL\d+T)/edit"

    def GET(self, key):
        tag = web.ctx.site.get(key)
        if tag is None:
            raise web.notfound()

        if not self.has_permission(tag):
            return render_template(
                "permission_denied",
                web.ctx.fullpath,
                "Permission denied to edit " + key + ".",
            )

        i = web.input(redir=None)
        return render_template("type/tag/form", tag, redirect=i.redir)

    def POST(self, key):
        tag = web.ctx.site.get(key)
        if tag is None:
            raise web.notfound()

        if not self.has_permission(tag):
            return render_template(
                "permission_denied",
                web.ctx.fullpath,
                "Permission denied to edit " + key + ".",
            )

        i = web.input(_comment=None, redir=None)
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
                    return render_template("type/tag/form", formdata, redirect=i.redir)

        try:
            if "_delete" in i:
                tag = web.ctx.site.new(key, {"key": key, "type": {"key": "/type/delete"}})
                tag._save(comment=i._comment, action="delete-tag")
                raise safe_seeother(key)
            tag.update(formdata)
            tag._save(comment=i._comment, action="edit-tag")
            raise safe_seeother(i.redir or key)
        except (ClientException, ValidationException) as e:
            add_flash_message("error", str(e))
            return render_template("type/tag/form", tag, redirect=i.redir)

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
        if not web.ctx.site.can_write(tag.key):
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

        tag_keys = web.ctx.site.things(q)
        has_next = len(tag_keys) > limit
        tags = web.ctx.site.get_many(tag_keys[:limit]) if tag_keys else []

        return render_template(
            "type/tag/index",
            tags=tags,
            page=page_num,
            has_next=has_next,
            tag_type=tag_type,
        )


def setup():
    """Do required setup."""
    pass
