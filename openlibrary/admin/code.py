import os

import web

from infogami.utils.view import render_template
from openlibrary.admin import utils
from openlibrary.core import admin

app = web.auto_application()
app.add_processor(utils.admin_processor)
app.notfound = utils.notfound


class home(app.page):  # type: ignore[name-defined]
    path = "/admin/?"

    def GET(self):
        stats = admin.get_stats()
        return render_template("admin/index", stats)


class static(app.page):  # type: ignore[name-defined]
    path = "(/(?:images|js|css)/.*)"

    def GET(self, path):
        raise web.seeother("/static/upstream" + path)


def setup():
    # load templates from this package so that they are available via render_template
    from infogami.utils import template  # noqa: PLC0415

    template.load_templates(os.path.dirname(__file__))
