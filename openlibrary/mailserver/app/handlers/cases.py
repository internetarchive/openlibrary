from email.parser import Parser
import logging

from lamson.routing import route, route_like, stateless
from config.settings import relay, support_db
from lamson import view
from lamson.queue import Queue

from openlibrary.core import support


@route("support\+(case)@(host)", case="[0-9]+")
@stateless
def CASE(message, case=None, host=None):
    print "I received a message from case %s"%case
    print "And I'm creating a case for it"
    q = Queue("run/cases")
    q.push(message)
    # Update case here
    try:
        case = support_db.get_case(case)
        m= Parser().parsestr(str(message))
        frm = m['From']
        payload = m.get_payload()
        case.add_worklog_entry(frm, payload)
    except support.InvalidCase:
        logging.warning("Attempt to update non existing case")
        # Send an email about this
    except Exception:
        logging.critical("Error while updating case", exc_info = True)
        

@route("(account)@(host)", account = "[^+]+", host=".+")
@stateless
def FORWARD(message, account=None, host=None):
    print "Forwarding message now %s, %s, %s"%(message, account, host)
    relay.deliver(message)
