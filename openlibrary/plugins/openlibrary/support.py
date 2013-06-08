import datetime

import web
import logging

from infogami import config
from infogami.utils import delegate
from infogami.utils.view import render_template

from openlibrary.core import support as S
from openlibrary import accounts
from openlibrary.core import stats

support_db = None

logger = logging.getLogger("openlibrary")

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

            url = web.ctx.home + url
            displayname = user and user.get_name() or ""
            username = user and user.get_username() or ""

            message = SUPPORT_EMAIL_TEMPLATE % locals()
            sendmail(email, assignee, subject, message)
        return render_template("email/case_created", assignee)

def sendmail(from_address, to_address, subject, message):
    if config.get('dummy_sendmail'):
        msg = ('' +
            'To: ' + to_address + '\n' +
            'From:' + from_address + '\n' +
            'Subject:' + subject + '\n' +
            '\n' +
            web.safestr(message))

        logger.info("sending email:\n%s", msg)
    else:
        web.sendmail(from_address, to_address, subject, message)

            
SUPPORT_EMAIL_TEMPLATE = """

Description:\n
%(description)s

A new support case has been filed by %(displayname)s <%(email)s>.

Topic: %(topic)s
URL: %(url)s
User-Agent: %(useragent)s
OL-username: %(username)s
"""

def setup():
    global support_db
    try:
        support_db = S.Support()
    except S.DatabaseConnectionError:
        support_db = None


