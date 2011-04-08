"""Script to send report of internal errors."""

import sys
import web
import os
import socket
from collections import defaultdict
from BeautifulSoup import BeautifulSoup
from optparse import OptionParser


TEMPLATE = """\
$def with (hostname, date, dir, errors)
$var subject: $dir: $date

$ error_places = group(errors, lambda e: (e.message, e.code))
$hostname.split('.')[0]/$date: $len(errors) errors at $len(error_places) places
$ newline = ""

$for (msg, code), elist in error_places[:10]:
    [$len(elist) times] $msg 
    at $code
    
    $ errgroup = group(elist, lambda e: e.url)
        $for url, x in errgroup[:3]:
            [$len(x) times] $url
            $x[0].error_url
            $newline
        $if len(errgroup) > 3:
            ...
            $newline        
$if len(error_places) > 10:
    ...
     
"""

hostname = socket.gethostname()
def group(items, key):
    d = defaultdict(list)
    for item in items:
        d[key(item)].append(item)
        
    return sorted(d.items(), reverse=True, key=lambda (k, vlist): len(vlist))

web.template.Template.globals.update({
    "sum": sum,
    "group": group,
})
t = web.template.Template(TEMPLATE)

def main():
    parser = OptionParser()
    parser.add_option("--email", dest="email", help="address to send email", action="append")
    options, args = parser.parse_args()
    
    dir, date = args
    
    msg = process_errors(dir, date)
    if options.email:
        web.sendmail(
            from_address='Open Library Errors<noreply@openlibrary.org>',
            to_address=options.email,
            subject=msg.subject,
            message=web.safestr(msg))
        print "email sent to", ", ".join(options.email)
    else:
        print msg
    
def process_errors(dir, date):
    root = os.path.join("/var/log/openlibrary", dir, date)
    
    basename = os.path.basename(dir)
    
    def parse(f):
        e = parse_error(os.path.join(root, f))
        e.error_url = "http://%s/logs/%s/%s/%s" % (hostname, basename, date, f)
        return e

    if os.path.exists(root):
        errors = [parse(f) for f in os.listdir(root)]
    else:
        errors = []
    
    return t(hostname, date, dir, errors)
    
def parse_error(path):
    html = open(path).read(10000)
    soup = BeautifulSoup(html)
    
    h1 = web.htmlunquote(soup.body.h1.string or "")
    h2 = web.htmlunquote(soup.body.h2.string or "")
    message = h1.split('at')[0].strip() + ': ' + (h2 and h2.splitlines()[0])

    code, url = [web.htmlunquote(td.string) for td in soup.body.table.findAll('td')]
    
    # strip common prefixes
    code = web.re_compile(".*/(?:staging|production)/(openlibrary|infogami|web)").sub(r'\1', code)
    
    m = web.re_compile('(\d\d)(\d\d)(\d\d)(\d{6})').match(web.numify(os.path.basename(path)))
    hh, mm, ss, microsec = m.groups()
    
    return web.storage(url=url, message=message, code=code, time="%s:%s:%s" % (hh, mm, ss))

if __name__ == "__main__":
    main()
