import datetime

import web

from infogami import config
from infogami.utils import delegate
from infogami.utils.view import render_template
from infogami.utils.context import context

from openlibrary.core import support as S

support_db = None

class contact(delegate.page):
    def GET(self):
        if not support_db:
            return "The Openlibrary support system is currently offline. Please try again later."
        i = web.input(path=None)
        email = context.user and context.user.email
        return render_template("support", email=email, url=i.path)

    def POST(self):
        if "support" in web.ctx.features:
            return self.POST_new()
        else:
            return self.POST_old()

    def POST_old(self):
        i = web.input(email='', url='', question='')
        fields = web.storage({
            'email': i.email,
            'irl': i.url,
            'comment': i.question,
            'sent': datetime.datetime.utcnow(),
            'browser': web.ctx.env.get('HTTP_USER_AGENT', '')
        })
        msg = render_template('email/spam_report', fields)
        web.sendmail(i.email, config.report_spam_address, msg.subject, str(msg))
        return render_template("support", done = True)

    def POST_new(self):
        if not support_db:
            return "Couldn't initialise connection to support database"
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
                                   creator_username  = user and user.get_username() or "",
                                   subject           = topic,
                                   description       = description,
                                   url               = url,
                                   assignee          = "mary@openlibrary.org")

        subject = "Case #%s: %s"%(c.caseno, topic)
        message = render_template("email/support_case", c)
        web.sendmail("support@openlibrary.org", email, subject, message)

        subject = "Case #%s created: %s"%(c.caseno, topic)
        notification = render_template("email/case_notification", c)
        web.sendmail("support@openlibrary.org", "info@openlibrary.org", subject, notification)

        return render_template("email/case_created", c)


def setup():
    global support_db
    try:
        support_db = S.Support()
    except S.DatabaseConnectionError:
        support_db = None


