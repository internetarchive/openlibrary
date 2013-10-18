from infogami import config
from infogami.utils.view import render_template
import web

def sendmail_with_template(template, to, cc=None, frm=None, **kwargs):
    msg = render_template(template, **kwargs)
    _sendmail(to, msg, cc=cc, frm=frm)

def _sendmail(to, msg, cc=None, frm=None):
    cc = cc or []
    frm = frm or config.from_address
    if config.get('dummy_sendmail'):
        message = ('' +
            'To: ' + to + '\n' +
            'From:' + config.from_address + '\n' +
            'Subject:' + msg.subject + '\n' +
            '\n' +
            web.safestr(msg))

        print >> web.debug, "sending email", message
    else:
        print >> web.debug, "sending email to %s - Subject: %s" % (to, msg.subject.strip())
        web.sendmail(frm, to, subject=msg.subject.strip(), message=web.safestr(msg), cc=cc)

