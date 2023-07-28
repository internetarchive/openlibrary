from infogami.utils import delegate
from infogami.utils.view import render_template, public
import web
import json

class tags_partials(delegate.page):
    path = "/tags/partials"
    encoding = "json"

    def GET(self):
        i = web.input(key=None)

        works = i.work_ids

        tagging_menu = render_template('tags/tagging_menu', works)

        partials = {
            'tagging_menu': str(tagging_menu),
        }

        return delegate.RawText(json.dumps(partials))