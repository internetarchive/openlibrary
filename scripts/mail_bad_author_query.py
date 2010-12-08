#!/usr/bin/python
import web, os, smtplib, sys
from email.mime.text import MIMEText

password = open(os.path.expanduser('~/.openlibrary_db_password')).read()
if password.endswith('\n'):
    password = password[:-1]
db_error = web.database(dbn='postgres', db='ol_errors', host='localhost', user='openlibrary', pw=password)
db_error.printing = False

body = '''When using the Open Library query interface the results should only include
authors. There shouldn't be any redirects or deleted authors in the results.

Below is a list of bad results for author queries from imports that have
run today.
'''

seen = set()
bad_count = 0
for row in db_error.query("select t, query, result from errors where t between 'yesterday' and 'today'"):
    author = row.query
    if author in seen:
        continue
    seen.add(author)
    bad_count += 1
    body += '-' * 60 + '\nAuthor name: ' + author + '\n'
    body += 'http://openlibrary.org/query.json?type=/type/author&name=%s' % web.urlquote(author) + '\n\n'
    body += row.result + '\n'

if bad_count == 0:
    sys.exit(0)

#print body

addr_from = 'edward@archive.org'
addr_to = 'openlibrary@archive.org'
#msg = MIMEText(body, 'plain', 'utf-8')
try:
    msg = MIMEText(body, 'plain', 'iso-8859-15')
except UnicodeEncodeError:
    msg = MIMEText(body, 'plain', 'utf-8')
msg['From'] = addr_from
msg['To'] = addr_to
msg['Subject'] = "import error report: %d bad author queries" % bad_count

s = smtplib.SMTP('mail.archive.org')
s.sendmail(addr_from, [addr_to], msg.as_string())
s.quit()
