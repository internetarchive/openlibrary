import re
import email
import imaplib
import logging as Logging
import logging.config
import ConfigParser
import os

import yaml
import couchdb
import web

from openlibrary.core import support

subject_re = re.compile("^(R[Ee]:)? ?Case #([0-9]+): .*")

template = """

%(message)s

-- Links --------------------------------------------
Case page : http://openlibrary.org/admin/support/%(caseno)s

"""

class Error(Exception): pass

# Utility functions for the imap coneection
def parse_imap_response(response):
    code, body = response
    message = email.message_from_string(body)
    logger.debug("Message parsed : %s (Subject : %s)", code, message.get('Subject',""))
    messageid = code.split()[0]
    return messageid, message

def imap_reset_to_unseen(imap_conn, messageid):
    logger.debug(" Resetting %s to unseen", messageid)
    imap_conn.store(messageid, "-FLAGS", r'(\Seen)')

def imap_move_to_folder(imap_conn, messageid, mailboxname):
    logger.debug(" Moving message %s to  %s ", messageid, mailboxname)
    imap_conn.copy(messageid, mailboxname)
    imap_mark_for_deletion(imap_conn, messageid)

def imap_mark_for_deletion(imap_conn, messageid):
    imap_conn.store(messageid, "+FLAGS", r'(\Deleted)')

def imap_remove_delete_flag(imap_conn, messageid):
    imap_conn.store(messageid, "-FLAGS", r'(\Deleted \Seen)')


def set_up_imap_connection(config_file, ol_config):
    try:
        c = ConfigParser.ConfigParser()
        c.read(config_file)
        username = c.get("support","username")
        password = c.get("support","password")
        email_server = ol_config.get("smtp_server")
        conn = imaplib.IMAP4_SSL(email_server)
        conn.login(username, password)
        conn.select("INBOX")
        logger.info("Connected to IMAP server")
        typ, data =  conn.status("INBOX", "(MESSAGES)")
        if typ == "OK":
            logger.info(" INBOX selected - status:%s", data)
        return conn
    except imaplib.IMAP4.error, e:
        logger.critical("Connection setup failure : credentials (%s, %s)", username, password, exc_info = True)
        raise Error(str(e))


def connect_to_admindb(config):
    db = config.get("admin",{}).get("admin_db",None)
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
        case.add_worklog_entry(author, message)
        case.change_status("new")
        logger.info("  Updated case")
    except support.InvalidCase:
        logger.info("  Invalid case %s message from %s", case.caseno, author)

    
def fetch_and_update(imap_conn, db_conn = None):
    for resp in get_new_emails(imap_conn):
        messageid, message = parse_imap_response(resp)
        m = subject_re.search(message['Subject'])
        if m:
            _, caseid = m.groups()
            logger.debug(" Updating case %s", caseid)
            try:
                frm = email.utils.parseaddr(message['From'])[1]
                case = db_conn.get_case(caseid)
                update_support_db(frm, message.get_payload(), case)
                imap_move_to_folder(imap_conn, messageid, "Accepted")
                message = template%dict(caseno = caseid,
                                        message = message.get_payload(),
                                        author = frm)
                subject = "Case #%s updated"%(caseid)
                assignee = case.assignee
                web.sendmail("support@openlibrary.org", assignee, subject, message)
            except Exception, e:
                logger.warning(" Couldn't update case. Resetting message", exc_info = True)
                imap_reset_to_unseen(imap_conn, messageid)
        else:
            logger.debug(" Ignoring message and resetting to unread")
            imap_move_to_folder(imap_conn, messageid, "Rejected")
    logger.debug("Expunging deleted messages")
    imap_conn.expunge()


def fetchmail(config):
    global logger
    logging.config.fileConfig(config.get('logging_config_file'))
    logger = Logging.getLogger("openlibrary.fetchmail")
    try:
        conn = set_up_imap_connection(config.get('email_config_file'), config)
        db_conn = connect_to_admindb(config)
        fetch_and_update(conn, db_conn)
        conn.close()
        conn.logout()
        return 0
    except KeyboardInterrupt:
        logger.info("User interrupt. Aborting")
        conn.close()
        conn.logout()
        return -1
    except Error:
        logger.info("Abnormal termination")
        return -2
        
def main(ol_config_file):
    config = yaml.load(open(ol_config_file))
    fetchmail(config)

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print "Usage : python fetchmail.py <openlibrary config file>"
        sys.exit(-2)
    sys.exit(main(*sys.argv[1:]))
