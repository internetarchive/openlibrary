import hashlib

import web
import logging

from infogami import config
from infogami.utils import delegate
from infogami.utils.view import render_template

from openlibrary import accounts
from openlibrary.core import stats
from openlibrary.core.cache import get_memcache
from openlibrary.plugins.upstream.addbook import get_recaptcha
from openlibrary.utils.dateutil import MINUTE_SECS

logger = logging.getLogger("openlibrary")


class contact(delegate.page):
    def GET(self):
        i = web.input(path=None)
        user = accounts.get_current_user()
        email = user and user.email

        hashed_ip = hashlib.md5(web.ctx.ip.encode('utf-8')).hexdigest()
        has_emailed_recently = get_memcache().get('contact-POST-%s' % hashed_ip)
        recaptcha = has_emailed_recently and get_recaptcha()
        return render_template("support", email=email, url=i.path, recaptcha=recaptcha)

    def POST(self):
        form = web.input()
        patron_name = form.get("name", "")
        email = form.get("email", "")
        topic = form.get("topic", "")
        subject_line = form.get('subject', '')
        description = form.get("question", "")
        url = form.get("url", "")
        user = accounts.get_current_user()
        useragent = web.ctx.env.get("HTTP_USER_AGENT", "")
        if not all([email, description]):
            return ""

        hashed_ip = hashlib.md5(web.ctx.ip.encode('utf-8')).hexdigest()
        has_emailed_recently = get_memcache().get('contact-POST-%s' % hashed_ip)
        if has_emailed_recently:
            recap = get_recaptcha()
            if recap and not recap.validate():
                return render_template(
                    "message.html",
                    'Recaptcha solution was incorrect',
                    (
                        'Please <a href="javascript:history.back()">go back</a> and try '
                        'again.'
                    ),
                )

        default_assignees = config.get("support_default_assignees", {})
        if (topic_key := str(topic.replace(" ", "_").lower())) in default_assignees:
            assignee = default_assignees.get(topic_key)
        else:
            assignee = default_assignees.get("default", "openlibrary@archive.org")
        stats.increment("ol.support.all")
        subject = "Support case *%s*" % self.prepare_subject_line(subject_line)

        url = web.ctx.home + url
        displayname = user and user.get_name() or ""
        username = user and user.get_username() or ""

        message = SUPPORT_EMAIL_TEMPLATE % locals()
        sendmail(email, assignee, subject, message)

        get_memcache().set(
            'contact-POST-%s' % hashed_ip, "true", expires=15 * MINUTE_SECS
        )
        return render_template("email/case_created", assignee)

    def prepare_subject_line(self, subject, max_length=60):
        if not subject:
            return '[no subject]'
        if len(subject) <= max_length:
            return subject

        return subject[:max_length]


def sendmail(from_address, to_address, subject, message):
    if config.get('dummy_sendmail'):
        msg = (
            f'To: {to_address}\n'
            f'From:{from_address}\n'
            f'Subject:{subject}\n'
            f'\n{web.safestr(message)}'
        )

        logger.info("sending email:\n%s", msg)
    else:
        web.sendmail(from_address, to_address, subject, message)


SUPPORT_EMAIL_TEMPLATE = """

Description:\n
%(description)s

A new support case has been filed by %(displayname)s <%(email)s>.

Subject: %(subject_line)s
URL: %(url)s
User-Agent: %(useragent)s
OL-username: %(username)s
Patron-name: %(patron_name)s
"""


def setup():
    pass
