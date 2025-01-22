"""Handlers for adding and editing tags."""

import web

from infogami.core.db import ValidationException
from infogami.infobase.client import ClientException
from infogami.utils import delegate
from infogami.utils.view import add_flash_message, public
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
    return (
        tag.get('name', '')
        and tag.get('tag_description', '')
        and tag.get('tag_type', '') in get_tag_types()
        and tag.get('body')
    )


def validate_subject_tag(tag):
    return validate_tag(tag) and tag.get('tag_type', '') in get_subject_tag_types()


def create_tag(tag: dict):
    if not validate_tag(tag):
        raise ValueError("Invalid data for tag creation")

    d = {
        "type": {"key": "/type/tag"},
        **tag,
    }

    tag = Tag.create(trim_doc(d))
    return tag


def create_subject_tag(tag: dict):
    if not validate_subject_tag(tag):
        raise ValueError("Invalid data for subject tag creation")

    d = {
        "type": {"key": "/type/tag"},
        **tag,
    }

    tag = Tag.create(trim_doc(d))
    return tag


def find_match(name: str, tag_type: str) -> str:
    """
    Tries to find an existing tag that matches the data provided by the user.
    Returns the key of the matching tag, or an empty string if no such tag exists.
    """
    matches = Tag.find(name, tag_type=tag_type)
    return matches[0] if matches else ''


class addtag(delegate.page):
    path = '/tag/add'

    def GET(self):
        """Main user interface for adding a tag to Open Library."""
        if not (patron := get_current_user()):
            # NOTE : will lose any query params on login redirect
            raise web.seeother(f'/account/login?redirect={self.path}')

        if not self.has_permission(patron):
            raise web.unauthorized(message='Permission denied to add tags')

        i = web.input(name=None, type=None, sub_type=None)

        return render_template('type/tag/form', i)

    def has_permission(self, user) -> bool:
        """
        Can a tag be added?
        """
        return user and (
            user.is_librarian() or user.is_super_librarian() or user.is_admin()
        )

    def POST(self):
        i = web.input(
            name="",
            tag_type="",
            tag_description="",
            body="",
        )

        if spamcheck.is_spam(i, allow_privileged_edits=True):
            return render_template(
                "message.html", "Oops", 'Something went wrong. Please try again later.'
            )

        if not (patron := get_current_user()):
            raise web.seeother(f'/account/login?redirect={self.path}')

        if not self.has_permission(patron):
            raise web.unauthorized(message='Permission denied to add tags')

        if not self.validate_input(i):
            raise web.badrequest()

        if match := find_match(i.name, i.tag_type):
            # A tag with the same name and type already exists
            add_flash_message(
                'error',
                f'A matching tag with the same name and type already exists: <a href="{match}">{match}</a>',
            )
            return render_template('type/tag/form', i)

        tag = create_tag(i)
        raise safe_seeother(tag.key)

    def validate_input(self, i):
        if i.tag_type in get_subject_tag_types():
            return validate_subject_tag(i)
        return validate_tag(i)


class tag_edit(delegate.page):
    path = r"(/tags/OL\d+T)/edit"

    def GET(self, key):
        if not web.ctx.site.can_write(key):
            return render_template(
                "permission_denied",
                web.ctx.fullpath,
                "Permission denied to edit " + key + ".",
            )
        i = web.input(redir=None)
        tag = web.ctx.site.get(key)
        if tag is None:
            raise web.notfound()

        return render_template("type/tag/form", tag, redirect=i.redir)

    def POST(self, key):
        if not web.ctx.site.can_write(key):
            return render_template(
                "permission_denied",
                web.ctx.fullpath,
                "Permission denied to edit " + key + ".",
            )
        tag = web.ctx.site.get(key)
        if tag is None:
            raise web.notfound()

        i = web.input(_comment=None, redir=None)
        formdata = trim_doc(i)
        if not formdata or not self.validate(formdata, formdata.tag_type):
            raise web.badrequest()
        if tag.tag_type != formdata.tag_type:
            match = find_match(formdata.name, formdata.tag_type)
            if match:
                # A tag with the same name and type already exists
                add_flash_message(
                    'error',
                    f'A matching tag with the same name and type already exists: <a href="{match}">{match}</a>',
                )
                return render_template("type/tag/form", formdata, redirect=i.redir)

        try:
            if "_delete" in i:
                tag = web.ctx.site.new(
                    key, {"key": key, "type": {"key": "/type/delete"}}
                )
                tag._save(comment=i._comment)
                raise safe_seeother(key)
            tag.update(formdata)
            tag._save(comment=i._comment)
            raise safe_seeother(i.redir if i.redir else key)
        except (ClientException, ValidationException) as e:
            add_flash_message('error', str(e))
            return render_template("type/tag/form", tag, redirect=i.redir)

    def validate(self, data, tag_type):
        if tag_type in SUBJECT_SUB_TYPES:
            return validate_subject_tag(data)
        else:
            return validate_tag(data)


class tag_search(delegate.page):
    path = "/tags/-/([^/]+):([^/]+)"

    def GET(self, type, name):
        # TODO : Search is case sensitive
        # TODO : Handle spaces and special characters
        matches = Tag.find(name, tag_type=type)
        if matches:
            return web.seeother(matches[0])
        return render_template("notfound", f"/tags/-/{type}:{name}", create=False)


def setup():
    """Do required setup."""
    pass
