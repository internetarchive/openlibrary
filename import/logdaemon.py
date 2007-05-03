import sys
sys.path.insert(0, "../infogami")

logfile = '/1/dbg/import-logs/dbglog'
logfile = '/1/pharos/db/authortest'
#logfile = '/tmp/log.test'
# outfile = sys.stdout
outfile = open('solr1.xml', 'w')

# solr = 'http://localhost:8983/solr/update'
solr = ('localhost', 1235)
solr = ('localhost', 8983)

from infogami.tdb.logger import parse, parse2a, parse2b
import web

import re
import socket
from itertools import *
from itools import *
from operator import itemgetter
fst = itemgetter(0)
snd = itemgetter(1)

def setup():
    web.config.db_parameters = dict(dbn="postgres",
                                    db="dbglog",
                                    user="pharos",
                                    pw="pharos")
    web.load()

#@slicer(5)
def logparse(logfile):
    return parse2b(parse(logfile,
                         infinite=False))

def speed():
    from time import time
    p = logparse(logfile)
    t0=time()
    n = sum(1 for x in p)
    dt = time()-t0
    print '%d items, %.3f seconds, %.2f items/sec'% (n, dt, n/dt)

setup()

# ================================================================

from exclude import excluded_fields

def main():
    global t,k
    # out = open('solr.xml', 'w')
    from time import time
    t1 = t0 = time()

    print >>outfile, "<add>"

    for i,t in enumerate(logparse(logfile)):
        # print list(k for k in t.d)
        if time()-t1 > 5 or i % 100 == 0:
            print (i, time()-t1, time()-t0)
            sys.stdout.flush()
            t1 = time()
        emit_doc (t)

    print >>outfile, "</add>"

def emit_doc(t):
    print >>outfile, "<document>"
    for k in t.d:
        assert k != 'text'
        v = getattr(t.d, k)
        emit_field(k, v)
        if k not in excluded_fields:
            emit_field('text', v)
    print >>outfile, "</document>\n"


def emit_field(field_name, field_val, non_strings = set()):
    from cgi import escape
    assert escape(field_name) == field_name

    if type(field_val) == list:
        for v in field_val:
            emit_field(field_name, v)
    else:
        # some fields are numeric--may need to pad these with
        # leading zeros for sorting purposes, but don't bother for now. @@
        if type(field_val) != str:
            field_val = str(field_val)
            if field_name not in non_strings:
                # temporarily print out names of fields which
                # are found to (sometimes) actually contain a
                # non-string value.
                print 'non-string fieldname', field_name
                non_strings.add(field_name)

        print >>outfile, "  <field name=%s>%s</field>"% (field_name,
                                                         escape(field_val))

def solr_submit(xml):
    """submit an XML document to solr"""
    sock = socket.socket()
    try:
        sock.connect(solr)
        sock.sendall('POST /solr/update HTTP/1.1\n')
        sock.sendall('Host: %s:%d\n'% solr)
        sock.sendall('Content-type:text/xml; charset=utf-8\n')
        sock.sendall('Content-Length: %d\n\n'% len(xml))
        sock.sendall(xml)
        response = sock.recv(10000)
    finally:
        sock.close()
    return response

main()
