import web

from infogami import config
from infogami.utils.view import render_template


def sendmail_with_template(template, to, cc=None, frm=None, **kwargs):
    msg = render_template(template, **kwargs)
    _sendmail(to, msg, cc=cc, frm=frm)


def _sendmail(to, msg, cc=None, frm=None):
    cc = cc or []
    frm = frm or config.from_address
    if config.get('dummy_sendmail'):
        message = (
            f'To: {to}\n'
            f'From:{config.from_address}\n'
            f'Subject:{msg.subject}\n'
            f'\n{web.safestr(msg)}'
        )

        print("sending email", message, file=web.debug)
    else:
        web.sendmail(
            frm, to, subject=msg.subject.strip(), message=web.safestr(msg), cc=cc
        )
