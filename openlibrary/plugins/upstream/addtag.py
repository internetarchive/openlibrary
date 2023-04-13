"""Handlers for adding and editing tags."""

import io
import itertools
import web
import json
import csv
import datetime

from typing import NoReturn

from infogami import config
from infogami.core import code as core
from infogami.core.db import ValidationException
from infogami.utils import delegate
from infogami.utils.view import safeint, add_flash_message
from infogami.infobase.client import ClientException

from openlibrary.plugins.openlibrary.processors import urlsafe
from openlibrary.i18n import gettext as _
import logging

from openlibrary.plugins.upstream import spamcheck, utils
from openlibrary.plugins.upstream.models import Tag
from openlibrary.plugins.upstream.addbook import get_recaptcha, safe_seeother, new_doc
from openlibrary.plugins.upstream.utils import render_template

logger = logging.getLogger("openlibrary.tag")


class addtag(delegate.page):
    path = '/tag/add'

    def GET(self):
        """Main user interface for adding a tag to Open Library."""

        if not self.has_permission():
            return safe_seeother(f"/account/login?redirect={self.path}")

        return render_template('tag/add', recaptcha=get_recaptcha())

    def has_permission(self) -> bool:
        """
        Can a tag be added?
        """
        return web.ctx.site.can_write("/tag/add")

    def POST(self):
        i = web.input(
            tag_name="",
            tag_type="",
            tag_description="",
        )

        if spamcheck.is_spam(i, allow_privileged_edits=True):
            return render_template(
                "message.html", "Oops", 'Something went wrong. Please try again later.'
            )

        if not web.ctx.site.get_user():
            recap = get_recaptcha()
            if recap and not recap.validate():
                return render_template(
                    'message.html',
                    'Recaptcha solution was incorrect',
                    'Please <a href="javascript:history.back()">go back</a> and try again.',
                )

        i = utils.unflatten(i)
        match = self.find_match(i)  # returns None or Tag (if match found)

        if match and match.key.startswith('/tags'):
            # tag match
            tag = match
            return self.tag_match(tag)
        else:
            # no match
            return self.no_match(i)

    def find_match(self, i: web.utils.Storage) -> None | Tag:
        """
        Tries to find an existing tag that matches the data provided by the user.

        Case#1: No match. None is returned.
        Case#2: Tag match. Tag is returned.

        :param web.utils.Storage i: addtag user supplied formdata
        :return: None or Tag.
        """

        q = {'type': '/type/tag', 'name': i.name, 'tag_type': i.type}
        match = list(web.ctx.site.things(q))

        if len(match) == 0:
            return None  # Case 1, from add page
        else:
            return match[0]  # Case 2

    def tag_match(self, tag: Tag) -> NoReturn:
        """
        Action for when an existing tag has been found.
        Redirect user to the found tag's edit page to add any missing details.
        """
        raise safe_seeother(tag.url("/edit"))

    def no_match(self, i: web.utils.Storage) -> NoReturn:
        """
        Action to take when no tags are found.
        Creates a new Tag.
        Redirects the user to the tag edit page
        in `add-tag` mode.
        """
        tag = new_doc(
            "/type/tag", name=i.tag_name, type=i.tag_type, description=i.tag_description
        )

        web.ctx.site.save(tag, comment="Created new tag.")

        raise safe_seeother(tag.url("/edit"))


# remove existing definitions of addtag
delegate.pages.pop('/addtag', None)


class addtag(delegate.page):  # type: ignore[no-redef] # noqa: F811
    def GET(self):
        raise web.redirect("/tag/add")


# class tag_edit(delegate.page):
#     path = r"(/tags/OL\d+T)/edit"

#     def GET(self, key):
#         i = web.input(v=None, _method="GET")
#         v = i.v and safeint(i.v, None)

#         if not web.ctx.site.can_write(key):
#             return render_template(
#                 "permission_denied",
#                 web.ctx.fullpath,
#                 "Permission denied to edit " + key + ".",
#             )

#         tag = web.ctx.site.get(key, v)
#         if tag is None:
#             raise web.notfound()

#         return render_template('tags/edit', tag, recaptcha=get_recaptcha())

#     def POST(self, key):
#         i = web.input(v=None, _method="GET")

#         if spamcheck.is_spam(allow_privileged_edits=True):
#             return render_template(
#                 "message.html", "Oops", 'Something went wrong. Please try again later.'
#             )

#         recap = get_recaptcha()

#         if recap and not recap.validate():
#             return render_template(
#                 "message.html",
#                 'Recaptcha solution was incorrect',
#                 'Please <a href="javascript:history.back()">go back</a> and try again.',
#             )

#         v = i.v and safeint(i.v, None)
#         tag = web.ctx.site.get(key, v)
#         if tag is None:
#             raise web.notfound()

#         try:
#             helper = SaveTagHelper(tag, None)  # TODO: add SaveTagHelper
#             helper.save(web.input())
#             add_flash_message("info", utils.get_message("flash_tag_updated"))
#             raise safe_seeother(tag.url())
#         except (ClientException, ValidationException) as e:
#             add_flash_message('error', str(e))
#             return self.GET(key)


def setup():
    """Do required setup."""
    pass
