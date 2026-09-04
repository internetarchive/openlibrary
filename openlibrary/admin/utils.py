"""utils for admin application."""

import web

from infogami.utils import delegate, features
from infogami.utils.view import render_template
from openlibrary.core.jinja import render_jinja_template


def admin_processor(handler):
    """web.py application processor for enabling infogami and verifying admin permissions."""
    delegate.initialize_context()
    delegate.context.features = []
    features.loadhook()

    # required to give a special look and feel in site template
    delegate.context.setdefault("cssfile", "admin")
    delegate.context.setdefault("usergroup", "admin")

    page = handler()
    return render_jinja_template("site.html.jinja", page=page)


def notfound():
    page = render_template("notfound", web.ctx.path, create=False)
    msg = render_jinja_template("site.html.jinja", page=page)
    return web.notfound(msg)
