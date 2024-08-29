"""Handlers for adding and editing tags."""

import web

from typing import NoReturn

from infogami.core.db import ValidationException
from infogami.utils.view import add_flash_message, public
from infogami.infobase.client import ClientException
from infogami.utils import delegate

from openlibrary.accounts import get_current_user
from openlibrary.plugins.upstream import spamcheck, utils
from openlibrary.plugins.upstream.models import Tag
from openlibrary.plugins.upstream.addbook import safe_seeother, trim_doc
from openlibrary.plugins.upstream.utils import render_template
from openlibrary.plugins.worksearch.subjects import get_subject


@public
def get_tag_types():
    return ["subject", "work", "collection"]


def validate_tag(tag):
    return tag.get('name', '') and tag.get('tag_type', '')


class addtag(delegate.page):
    path = '/tag/add'

    def GET(self):
        """Main user interface for adding a tag to Open Library."""
        if not (patron := get_current_user()):
            raise web.seeother(f'/account/login?redirect={self.path}')

        if not self.has_permission(patron):
            raise web.unauthorized(message='Permission denied to add tags')

        i = web.input(name=None, type=None, sub_type=None, fkey=None)

        return render_template('tag/add', i.name, i.type, subject_type=i.sub_type, fkey=i.fkey)

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
            fkey=None,
        )

        if spamcheck.is_spam(i, allow_privileged_edits=True):
            return render_template(
                "message.html", "Oops", 'Something went wrong. Please try again later.'
            )

        if not (patron := get_current_user()):
            raise web.seeother(f'/account/login?redirect={self.path}')

        if not self.has_permission(patron):
            raise web.unauthorized(message='Permission denied to add tags')

        i = utils.unflatten(i)

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
        return Tag.find(i.name, i.tag_type)

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
        tag = Tag.create(i.name, i.tag_description, i.tag_type, fkey=i.fkey)
        if i.fkey:
            subject = get_subject(
                i.fkey,
                details=True,
                filters={'public_scan_b': 'false', 'lending_edition_s': '*'},
                sort=web.input(sort='readinglog').sort
            )
            if subject and subject.work_count > 0:
                tag.body = str(render_template('subjects', page=subject))
                tag._save()
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

        return render_template('type/tag/edit', tag)

    def POST(self, key):
        tag = web.ctx.site.get(key)
        if tag is None:
            raise web.notfound()

        i = web.input(_comment=None)
        formdata = self.process_input(i)
        try:
            if not formdata or not validate_tag(formdata):
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
        i = utils.unflatten(i)
        tag = trim_doc(i)
        return tag


def setup():
    """Do required setup."""
    pass
