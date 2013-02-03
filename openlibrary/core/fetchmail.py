import re
import email
import imaplib
import logging as Logging
import logging.config
import ConfigParser
import optparse
import quopri
import base64

import yaml
import couchdb
import web

from openlibrary.core import support
from infogami.utils.markdown import markdown

subject_re = re.compile("^.*[Cc]ase #([0-9]+).*")

template = """

%(message)s

-- Links --------------------------------------------
Case page : http://openlibrary.org/admin/support/%(caseno)s

"""

class Error(Exception): pass

# Utility functions for the imap coneection
def parse_email_subject(message):
    subject = message.get('Subject',"")
    if subject:
        if subject.startswith("=?utf-8"):
            subject = base64.decodestring(subject.split("?")[3])
    return subject
        
def parse_imap_response(response):
    code, body = response
    message = email.message_from_string(body)
    subject = parse_email_subject(message)
    logger.debug("Message parsed : %s (Subject : %s)", code, subject)
    messageid = code.split()[0]
    return messageid, message, subject

def imap_reset_to_unseen(imap_conn, messageid):
    logger.debug(" Resetting %s to unseen", messageid)
    imap_conn.store(messageid, "-FLAGS", r'(\Seen)')

def imap_move_to_folder(imap_conn, messageid, mailboxname, debug):
    if debug:
        logger.info("Debug mode: Not moving emails")
        return
    logger.debug(" Moving message %s to  %s ", messageid, mailboxname)
    imap_conn.copy(messageid, mailboxname)
    imap_mark_for_deletion(imap_conn, messageid)

def imap_mark_for_deletion(imap_conn, messageid):
    imap_conn.store(messageid, "+FLAGS", r'(\Deleted)')

def imap_remove_delete_flag(imap_conn, messageid):
    imap_conn.store(messageid, "-FLAGS", r'(\Deleted \Seen)')


def set_up_imap_connection(settings):
    email_config_file = settings.config.get('email_config_file')
    ol_config = settings.config
    try:
        c = ConfigParser.ConfigParser()
        c.read(email_config_file)
        username = settings.user or c.get("support","username")
        password = settings.password or c.get("support","password")
        imap_server = settings.imap or ol_config.get("smtp_server") # The key is badly named but it is the IMAP server.
        mailbox = settings.mailbox
        logger.debug("Connecting to %s using %s:%s and using mailbox %s", imap_server, username, password, mailbox)
        conn = imaplib.IMAP4_SSL(imap_server)
        conn.login(username, password)
        conn.select(mailbox)
        logger.info("Connected to IMAP server")
        typ, data =  conn.status(mailbox, "(MESSAGES)")
        if typ == "OK":
            logger.info(" %s selected - status:%s", mailbox, data)
        return conn
    except imaplib.IMAP4.error, e:
        logger.critical("Connection setup failure : credentials (%s, %s)", username, password, exc_info = True)
        raise Error(str(e))

def connect_to_admindb(settings):
    if settings.debug:
        return None 
    config = settings.config
    db = settings.couch or config.get("admin",{}).get("admin_db",None)
    logger.debug("Connected to couch db : %s", db)
    support_db = support.Support(couchdb.Database(db))
    return support_db
    
def get_new_emails(conn):
    typ, data = conn.search(None, "ALL")
    logger.debug("Fetching new message headers")
    for num in data[0].split():
        typ, data = conn.fetch(num, '(RFC822)')
        if typ != "OK":
            logger.warn("Message %s reported non okay status - %s", num, typ)
        yield data[0]


def update_support_db(author, message, case):
    try: 
        case.add_worklog_entry(author, unicode(message, errors="ignore"))
        case.change_status("new", author)
        logger.info("  Updated case #%s"%case.caseno)
    except support.InvalidCase:
        logger.info("  Invalid case %s message from %s", case.caseno, author)

def get_casenote(message):
    "Try to extract the casenote out of the message"
    md = markdown.Markdown()        
    ctype = message.get_content_type()
    if ctype == "multipart/related" or ctype == "multipart/signed" or ctype == "multipart/mixed":
        # Look inside for something we can use.
        for i in message.get_payload():
            ctype2 = i.get_content_type()
            if ctype2 == "multipart/alternative" or ctype2 == "text/plain" or ctype2 == "text/html": 
                message = i
    post_process = lambda x : x
    if message.get('Content-Transfer-Encoding') == "base64":
        post_process = base64.decodestring

    if message.get_content_type() == "text/plain":
        return quopri.decodestring(post_process(message.get_payload()))

    if message.get_content_type() == "text/html":
        casenote = md.convert(post_process(message.get_payload()))
        return casenote

    if message.get_content_type() == "multipart/alternative":
        # Find something we can use
        plain = html = None
        for part in message.get_payload():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                plain = post_process(part.get_payload(None, True))
            if content_type == "text/html":
                html  = post_process(part.get_payload(None, True))
        if not plain and not html:
            pieces = ",".join(x.get_content_type() for x in message.get_payload())
            logger.warning("This message has no usable payload Types : %s", pieces)
            return "ERROR : Unparseable message received"
        if plain:
            return quopri.decodestring(plain)
        if html:
            return md.convert(html)

def fetch_and_update(settings, imap_conn, db_conn = None):
    debug = settings.debug
    smtp_server = settings.smtp
    accept_mailbox = settings.accept_mailbox
    reject_mailbox = settings.reject_mailbox
    for resp in get_new_emails(imap_conn):
        try:
            messageid, message, subject = parse_imap_response(resp)
        except Exception, e:
            logger.warning(" Message parsing failed", exc_info = True)
            continue
        m = subject_re.search(subject)
        if m:
            caseid = m.groups()[0]
            logger.debug(" Updating case %s", caseid)
            try:
                frm = email.utils.parseaddr(message['From'])[1]
                casenote = get_casenote(message)
                if settings.debug:
                    logger.debug("Debug mode: Not touching couch database")
                    logger.debug("Case #%s would be updated by '%s' with \n-----\n%s\n-----",caseid, frm, casenote)
                    case = lambda:0 # To make the assignee checking work in debug mode
                    case.assignee = None
                else:
                    case = db_conn.get_case(caseid)
                    update_support_db(frm, casenote, case)

                imap_move_to_folder(imap_conn, messageid, accept_mailbox, debug)
                message = template%dict(caseno = caseid,
                                        message = casenote,
                                        author = frm)
                subject = "Case #%s updated"%(caseid)
                assignee = settings.to or case.assignee # Use the override address if specified. 
                                                        # Otherwise, to the assignee of the case
                if smtp_server:
                    web.config.smtp_server = smtp_server
                logger.debug("Sending notification from 'support@openlibrary.org' to '%s'", assignee)
                web.sendmail("support@openlibrary.org", assignee, subject, message)
            except Exception, e:
                logger.warning(" Couldn't update case. Resetting message", exc_info = True)
                imap_reset_to_unseen(imap_conn, messageid)
        else:
            logger.debug(" No regexp match on subject '%s'", subject)
            logger.debug("  Ignoring message and resetting to unread")
            imap_move_to_folder(imap_conn, messageid, reject_mailbox, debug)
    logger.debug("Expunging deleted messages")
    imap_conn.expunge()


def fetchmail(settings):
    global logger
    logging.config.fileConfig(settings.config.get('logging_config_file'))
    logger = Logging.getLogger("openlibrary")
    if settings.verbose:
        logger.setLevel(logging.DEBUG)
        for l in logger.handlers:
            l.setLevel(logging.DEBUG)
    try:
        imap_conn = set_up_imap_connection(settings)
        db_conn = connect_to_admindb(settings)
        fetch_and_update(settings, imap_conn, db_conn)
        imap_conn.close()
        imap_conn.logout()
        return 0
    except KeyboardInterrupt:
        logger.info("User interrupt. Aborting")
        imap_conn.close()
        imap_conn.logout()
        return -1
    except Error:
        logger.info("Abnormal termination")
        return -2

def parse_args(args):
    parser = optparse.OptionParser(usage = "usage: %prog [options] config_file")
    parser.add_option("-d", "--debug", dest="debug", action="store_true", help="Dry run (don't modify anything or send emails)")
    parser.add_option("-u", "--user", dest="user", action = "store", help="Specify IMAP username (overrides config)")
    parser.add_option("-p", "--password", dest="password", help="Specify IMAP password (overrides config)")
    parser.add_option("-i", "--imap", dest="imap", action = "store", help="IMAP server (overrides config)")
    parser.add_option("-s", "--smtp", dest="smtp", action = "store", default = "", help="SMTP server (overrides config)")
    parser.add_option("-m", "--mailbox", dest="mailbox", default = "INBOX", action = "store", help="Mailbox to look for emails in")
    parser.add_option("-a", "--accept-mailbox", dest="accept_mailbox", default = "Accepted", action = "store", help="Mailbox to move successfully parsed emails into")
    parser.add_option("-r", "--reject-mailbox", dest="reject_mailbox", default = "Rejected", action = "store", help="Mailbox to move emails which couldn't be processed into")
    parser.add_option("-t", "--to", dest="to", action = "store", default = "", help="Send notification emails to this address")
    parser.add_option("-v", "--verbose", dest="verbose", action = "store_true", default = False, help = "Enable debug output")
    parser.add_option("-c", "--couch", dest="couch", action = "store", help = "Couch database to use")

    opts, args = parser.parse_args(args)
    if not args:
        parser.error("No config file specified")
    return opts, args
        
def main(args):
    settings, args = parse_args(args)
    settings.config = yaml.load(open(args[0]))
    fetchmail(settings)

if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
