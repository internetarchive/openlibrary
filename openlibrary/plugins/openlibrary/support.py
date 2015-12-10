import datetime

import web
import logging

from infogami import config
from infogami.utils import delegate
from infogami.utils.view import render_template

from openlibrary import accounts
from openlibrary.core import stats

logger = logging.getLogger("openlibrary")

class contact(delegate.page):
    def GET(self):
        i = web.input(path=None)
        user = accounts.get_current_user()
        email = user and user.email
        return render_template("support", email=email, url=i.path)

    def POST(self):
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
            assignee = default_assignees.get(topic_key)
        else:
            assignee = default_assignees.get("default", "openlibrary@archive.org")
        stats.increment("ol.support.all")
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
    pass

