"""Handlers for adding and editing tags."""

from typing import NoReturn

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


SUBJECT_SUB_TYPES = ["subject", "person", "place", "time"]
TAG_TYPES = SUBJECT_SUB_TYPES + ["collection"]


@public
def get_tag_types():
    return TAG_TYPES


@public
def get_subject_tag_types():
    return SUBJECT_SUB_TYPES


def validate_tag(tag):
    return tag.get('name', '') and tag.get('tag_type', '') in get_tag_types()


def validate_subject_tag(tag):
    return tag.get('name', '') and tag.get('tag_type', '') in get_subject_tag_types() and tag.get('body')


def create_tag(tag: dict) -> Tag:
    if not validate_tag(tag):
        raise ValueError("Invalid data for tag creation")

    d = {
        "type": {"key": "/type/tag"},
        **tag,
    }

    tag = Tag.create(trim_doc(d))
    return tag


def create_subject_tag(tag: dict) -> Tag:
    if not validate_subject_tag(tag):
        raise ValueError("Invalid data for subject tag creation")

    d = {
        "type": {"key": "/type/tag"},
        **tag,
    }

    # TODO : handle case where body is empty string
    tag = Tag.create(trim_doc(d))
    return tag


class addtag(delegate.page):
    path = '/tag/add'

    def GET(self):
        """Main user interface for adding a tag to Open Library."""
        if not (patron := get_current_user()):
            raise web.seeother(f'/account/login?redirect={self.path}')

        if not self.has_permission(patron):
            raise web.unauthorized(message='Permission denied to add tags')

        i = web.input(name=None, type=None, sub_type=None)

        return render_template('tag/add', i)

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

        if not validate_tag(i):
            raise web.badrequest()

        match = self.find_match(i)  # returns None or Tag (if match found)

        if match:
            # tag match
            return self.tag_match(match)
        else:
            # no match
            return self.no_match(i)

    def find_match(self, i: web.utils.Storage):
        """
        Tries to find an existing tag that matches the data provided by the user.
        """
        matches =  Tag.find(i.name, tag_type=i.tag_type)
        return matches[0] if matches else None

    def tag_match(self, match: list) -> NoReturn:
        """
        Action for when an existing tag has been found.
        Redirect user to the found tag's edit page to add any missing details.
        """
        tag = web.ctx.site.get(match[0])
        raise safe_seeother(tag.key + "/edit")

    def no_match(self, i: web.utils.Storage) -> NoReturn:
        """
        Action to take when no tags are found.
        Creates a new Tag.
        Redirects the user to the tag's home page
        """
        tag = create_tag(i)
        raise safe_seeother(tag.key)


class tag_edit(delegate.page):
    path = r"(/tags/OL\d+T)/edit"

    def GET(self, key):
        if not web.ctx.site.can_write(key):
            return render_template(
                "permission_denied",
                web.ctx.fullpath,
                "Permission denied to edit " + key + ".",
            )

        tag = web.ctx.site.get(key)
        if tag is None:
            raise web.notfound()

        if tag.tag_type in SUBJECT_SUB_TYPES:
            return render_template("type/tag/subject/edit", tag)
        elif tag.tag_type == "collection":
            return render_template("type/tag/collection/edit", tag)

        return render_template('type/tag/edit', tag)

    def POST(self, key):
        tag = web.ctx.site.get(key)
        if tag is None:
            raise web.notfound()

        i = web.input(_comment=None)
        formdata = self.process_input(i)
        try:
            if not formdata or not self.validate(formdata, tag.tag_type):
                raise web.badrequest()
            elif "_delete" in i:
                tag = web.ctx.site.new(
                    key, {"key": key, "type": {"key": "/type/delete"}}
                )
                tag._save(comment=i._comment)
                raise safe_seeother(key)
            else:
                tag.update(formdata)
                tag._save(comment=i._comment)
                raise safe_seeother(key)
        except (ClientException, ValidationException) as e:
            add_flash_message('error', str(e))
            return render_template("type/tag/edit", tag)

    def process_input(self, i):
        tag = trim_doc(i)
        return tag

    def validate(self, data, tag_type):
        if tag_type in SUBJECT_SUB_TYPES:
            return validate_subject_tag(data)
        else:
            return validate_tag(data)


class add_typed_tag(delegate.page):
    path = "/tag/([^/]+)/add"

    def GET(self, tag_type):
        if not self.validate_type(tag_type):
            raise web.badrequest()
        if not (patron := get_current_user()):
            # NOTE : will lose any query params on login redirect
            raise web.seeother(f'/account/login?redirect={self.path}')
        if not self.has_permission(patron):
            raise web.unauthorized()

        i = web.input(tag_type=tag_type)
        if tag_type in get_subject_tag_types():
            return render_template("type/tag/subject/edit", i)
        return render_template(f"type/tag/{tag_type}/edit", i)

    def POST(self, tag_type):
        i = web.input(tag_type=tag_type)
        if not self.validate_type(i.tag_type) or not self.validate_input(i):
            raise web.badrequest()
        if spamcheck.is_spam(i, allow_privileged_edits=True):
            return render_template(
                "message.html", "Oops", 'Something went wrong. Please try again later.'
            )
        if not (patron := get_current_user()):
            raise web.seeother(f'/account/login')
        if not self.has_permission(patron):
            raise web.unauthorized()

        if i.tag_type in get_subject_tag_types():
            tag = create_subject_tag(i)
        else:
            tag = create_tag(i)
        raise safe_seeother(tag.key)

    def has_permission(self, user):
        return user and (
            user.is_librarian() or user.is_super_librarian() or user.is_admin()
        )

    def validate_type(self, tag_type):
        return tag_type in get_tag_types()

    def validate_input(self, i):
        if i.tag_type in get_subject_tag_types():
            return validate_subject_tag(i)
        return validate_tag(i)


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
