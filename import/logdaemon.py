import sys
sys.path.insert(0, "../infogami")

logfile = '/1/dbg/import-logs/dbglog'
logfile = '/1/pharos/db/authortest'
#logfile = '/tmp/log.test'
outfile = sys.stdout
outfile = open('solr1.xml', 'w')

# tcp socket of solr server
solr = ('localhost', 8983)

from infogami.tdb.logger import parse, parse1, parse2a, parse2b
import web

import re
import socket
from itertools import *
from itools import *
from cStringIO import StringIO
from operator import itemgetter

fst = itemgetter(0)
snd = itemgetter(1)

def setup():
    web.config.db_parameters = dict(dbn="postgres",
                                    db="dbglog",
                                    user="pharos",
                                    pw="pharos")
    web.load()

@slicer(10000)
def logparse(log_fd):
    return parse2b(parse1(log_fd,
                          infinite=True))

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

    log_fd = open(logfile)
    lastpos_fd = open('lastpos', 'r+', 0)
    lastpos = int(open('lastpos').readline())
    print 'seeking to %d'% lastpos
    log_fd.seek(lastpos)

    for i,t in enumerate(logparse(log_fd)):
        outbuf = StringIO()
        print >>outbuf, "<add>"

        if time()-t1 > 5 or i % 100 == 0:
            print (i, time()-t1, time()-t0)
            sys.stdout.flush()
            t1 = time()
        emit_doc (outbuf, t)

        print >>outbuf, "</add>"

        outfile.write(outbuf.getvalue())
        outfile.flush()

        lastpos_fd.seek(0)
        log_pos = log_fd.tell()
        lastpos_fd.write('%d\n'% log_pos)
        lastpos_fd.flush()

    lastpos_fd.close()

# dict of fields for which there will be a corresponding sortable
# field.  The field values will have to be transformed into a
# sorting key that does stuff like strips punctuation and folds
# case, or inserts leading zeros for numeric fields,
# but for now we just use the identity function.  The
# dict entries are of the form:
#     fieldname : (new field name, conversion function)

def identity(x): return x

sorted_field_dict = {
    'author': ('creatorSorter', identity),
    'title': ('titleSorter', identity),
    # there may also be something for dates here.  @@
    }

ids_seen = set()

def emit_doc(outbuf, t):
    assert t.name not in ids_seen
    for forbidden in ('text', 'identifier'):
        assert forbidden not in t.d
    ids_seen.add(t.name)

    print >>outbuf, "<document>"
    emit_field(outbuf, 'identifier', t.name)

    for k in t.d:
        v = getattr(t.d, k)
        emit_field(outbuf, k, v)
        if k not in excluded_fields:
            emit_field(outbuf, 'text', v)
        if k in sorted_field_dict:
            sfname, conversion = sorted_field_dict[k]
            emit_field(outbuf, sfname, conversion(v))
                       
    print >>outbuf, "</document>\n"
    return outbuf.getvalue()

def emit_field(outbuf,
               field_name,
               field_val,
               non_strings = set()):
    from cgi import escape
    assert escape(field_name) == field_name

    if type(field_val) == list:
        for v in field_val:
            emit_field(outbuf, field_name, v)
    else:
        # some fields are numeric--may need to pad these with
        # leading zeros for sorting purposes, but don't bother for now. @@
        if type(field_val) != str:
            field_val = str(field_val)
            if field_name not in non_strings:
                # temporarily print out names of fields which
                # are found to (sometimes) actually contain a
                # non-string value. @@
                print 'non-string fieldname', field_name
                non_strings.add(field_name)

        print >>outbuf, "  <field name=%s>%s</field>"% (field_name,
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
