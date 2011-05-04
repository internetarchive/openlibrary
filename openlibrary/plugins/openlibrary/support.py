
import web

from infogami.utils import delegate
from infogami.utils.view import render_template

from openlibrary.core import support as S

support_db = None

class support(delegate.page):
    def GET(self):
        return render_template("support")

    def POST(self):
        form = web.input()
        email = form.get("email", "")
        topic = form.get("topic", "")
        description = form.get("question", "")
        url = form.get("url", "")
        user = web.ctx.site.get_user()
        useragent = web.ctx.env.get("HTTP_USER_AGENT","")
        c = support_db.create_case(creator_name      = user and user.get_name() or "",
                                   creator_email     = email,
                                   creator_useragent = useragent,
                                   subject           = topic,
                                   description       = description,
                                   assignee          = "mary@archive.org") # TBD. This has to be dynamic
        return render_template("support", done = True)


def setup():
    global support_db
    support_db = S.Support()

