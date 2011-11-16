import datetime

import web

from infogami import config
from infogami.utils import delegate
from infogami.utils.view import render_template
from infogami.utils.context import context

from openlibrary.core import support as S
from openlibrary import accounts

support_db = None

class contact(delegate.page):
    def GET(self):
        if not support_db:
            return "The Openlibrary support system is currently offline. Please try again later."
        i = web.input(path=None)
        user = accounts.get_current_user()
        email = user and user.email
        return render_template("support", email=email, url=i.path)

    def POST(self):
        if not support_db:
            return "Couldn't initialise connection to support database"
        form = web.input()
        email = form.get("email", "")
        topic = form.get("topic", "")
        description = form.get("question", "")
        url = form.get("url", "")
        user = accounts.get_current_user()
        useragent = web.ctx.env.get("HTTP_USER_AGENT","")
        if not all([email, topic, description]):
            return ""
        c = support_db.create_case(creator_name      = user and user.get_name() or "",
                                   creator_email     = email,
                                   creator_useragent = useragent,
                                   creator_username  = user and user.get_username() or "",
                                   subject           = topic,
                                   description       = description,
                                   url               = url,
                                   assignee          = config.get("support_case_default_address","mary@openlibrary.org"))

        # Send an email to the creator of the case
        subject = "Case #%s: %s"%(c.caseno, topic)
        message = render_template("email/support_case", c)
        web.sendmail(config.get("support_case_control_address","support@openlibrary.org"), 
                     email, subject, message)

        return render_template("email/case_created", c)


def setup():
    global support_db
    try:
        support_db = S.Support()
    except S.DatabaseConnectionError:
        support_db = None


