import datetime

import web

from infogami import config
from infogami.utils import delegate
from infogami.utils.view import render_template

from openlibrary.core import support as S
from openlibrary import accounts
from openlibrary.core import stats

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
        # if not support_db:
        #     return "Couldn't initialise connection to support database"
        form = web.input()
        email = form.get("email", "")
        topic = form.get("topic", "")
        description = form.get("question", "")
        url = form.get("url", "")
        user = accounts.get_current_user()
        useragent = web.ctx.env.get("HTTP_USER_AGENT","")
        if not all([email, topic, description]):
            return ""

        default_assignees = config.get("support_default_assignees",{})
        topic_key = str(topic.replace(" ","_").lower())
        if topic_key in default_assignees:
            # This is set to False to prevent cases from being created
            # even if there is a designated assignee. This prevents
            # the database from being updated.
            create_case = False 
            assignee = default_assignees.get(topic_key)
        else:
            create_case = False
            assignee = default_assignees.get("default", "mary@openlibrary.org")
        if create_case:
            c = support_db.create_case(creator_name      = user and user.get_name() or "",
                                       creator_email     = email,
                                       creator_useragent = useragent,
                                       creator_username  = user and user.get_username() or "",
                                       subject           = topic,
                                       description       = description,
                                       url               = url,
                                       assignee          = assignee)
            stats.increment("support.all")
        else:
            stats.increment("support.all")
            subject = "Support case *%s*"%topic
            message = "A new support case has been filed\n\nTopic: %s\n\nDescription:\n%s"%(topic, description)
            web.sendmail(email, assignee, subject, message)
        return render_template("email/case_created", assignee)
            
            


def setup():
    global support_db
    try:
        support_db = S.Support()
    except S.DatabaseConnectionError:
        support_db = None


