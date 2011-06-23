import re
import email
import imaplib
import logging as Logging
import logging.config
import ConfigParser


subject_re = re.compile("^(R[Ee]:)? ?Case #([0-9]+): .*")

logging.config.fileConfig("conf/logging.ini")
logger = Logging.getLogger("openlibrary.fetchmail")

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

def imap_mark_for_deletion(imap_conn, messageid):
    logger.debug(" Marking %s for deletion", messageid)
    imap_conn.store(messageid, "+FLAGS", r'(\Deleted)')

def imap_remove_delete_flag(imap_conn, messageid):
    logger.debug(" Removing deletion flag on  %s ", messageid)
    imap_conn.store(messageid, "-FLAGS", r'(\Deleted \Seen)')



def set_up_imap_connection(config_file):
    try:
        c = ConfigParser.ConfigParser()
        c.read(config_file)
        username = c.get("support","username")
        password = c.get("support","password")
        conn = imaplib.IMAP4_SSL("mail.archive.org")
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


def get_new_emails(conn):
    typ, data = conn.search(None, 'UNSEEN')
    logger.debug("Fetching new message headers")
    for num in data[0].split():
        typ, data = conn.fetch(num, '(RFC822)')
        if typ != "OK":
            logger.warn("Message %s reported non okay status - %s", num, typ)
        yield data[0]


def update_support_db(message, caseid, db):
    pass
    
def fetch_and_update(imap_conn, db_conn = None):
    for resp in get_new_emails(imap_conn):
        messageid, message = parse_imap_response(resp)
        m = subject_re.search(message['Subject'])
        if m:
            _, caseid = m.groups()
            logger.debug(" Updating case %s", caseid)
            try:
                update_support_db(message.get_payload(), caseid, db_conn)
                imap_mark_for_deletion(imap_conn, messageid)
            except Exception:
                logger.warning(" Couldn't update case. Resetting message", exc_info = True)
                imap_remove_delete_flag(imap_conn, messageid)
        else:
            logger.debug(" Ignoring message and resetting to unread")
            imap_reset_to_unseen(imap_conn, messageid)
    logger.debug("Expunging deleted messages")
    imap_conn.expunge()
        
        
def main(config_file):
    try:
        conn = set_up_imap_connection(config_file)
        fetch_and_update(conn)
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

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print "Usage : python fetchmail.py <password file>"
        sys.exit(-2)
    sys.exit(main(sys.argv[1]))
