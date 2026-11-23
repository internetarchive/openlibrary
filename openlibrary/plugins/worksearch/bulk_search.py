import web
from markupsafe import escape

from infogami import config  # noqa: F401 side effects may be needed
from infogami.utils import delegate
from openlibrary.core.jinja import render_jinja_template
from openlibrary.i18n import gettext as _


class bulk_search(delegate.page):
    path = "/search/bulk"

    def GET(self):
        body = render_jinja_template("bulk_search/bulk_search.html.jinja")
        # web.py's layout reads the title off the result, already escaped, as from Templetor's $var.
        return web.template.TemplateResult(__body__=body, title=escape(_("Bulk Search (beta)")))


def setup():
    pass
