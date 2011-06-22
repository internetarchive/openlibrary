import re
import email
import imaplib
import logging
import logging.config


subject_re = re.compile("^(R[Ee]:)? ?Case #([0-9]+): .*")

logging.config.fileConfig("conf/logging.ini")
logger = logging.getLogger("openlibrary.fetchmail")

def parse_imap_response(response):
    code, body = response
    message = email.message_from_string(body)
    logger.debug("Message parsed : %s ", code)
    logger.debug("Subject : %s", message.get('Subject',"None"))
    return code, message

def set_up_imap_connection():
    conn = imaplib.IMAP4_SSL("mail.archive.org")
    conn.login("support@openlibrary.org", "BigData")
    conn.select("INBOX")
    logger.info("Connected to IMAP server and INBOX selected")
    typ, data =  conn.status("INBOX", "(MESSAGES)")
    if typ == "OK":
        logger.info("INBOX selected - %s", data)
    return conn


def get_new_emails(conn):
    typ, data = conn.search(None, 'ALL')
    for num in data[0].split():
        typ, data = conn.fetch(num, '(RFC822)')
        if typ != "OK":
            logger.warn("Message %s reported non okay status - %s", num, typ)
        else:
            code, message = parse_imap_response(data[0]) # Parse the one email we've fetched
        yield message

def update_support_db(message, db):
    m = subject_re.search(message['Subject'])
    if m:
        d, caseid = m.groups()
        logger.debug(" Updating case %s", caseid)
    else:
        logger.debug(" Ignoring message")
    

def fetch_and_update(imap_conn, db_conn = None):
    for i in get_new_emails(imap_conn):
        update_support_db(i, db_conn)
        
        
def main():
    try:
        conn = set_up_imap_connection()
        fetch_and_update(conn)
    finally:
        conn.close()
        conn.logout()

if __name__ == "__main__":
    import sys
    sys.exit(main())
