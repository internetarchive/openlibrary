import web

from infogami.utils import delegate
from infogami.utils.view import query_param
from openlibrary.core.jinja import render_jinja_template
from openlibrary.i18n import gettext as _
from openlibrary.plugins.worksearch.code import random_author_search


def setup():
    pass


class author(delegate.page):
    path = "/authors"

    def GET(self):
        html = render_jinja_template(
            "authors/index.html.jinja",
            results=random_author_search(),
            q=query_param("q", ""),
        )
        return web.template.TemplateResult(__body__=html, title=_("Authors"))
