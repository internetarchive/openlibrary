import sys
sys.path.insert(0, "../infogami")

logfile = '/1/dbg/import-logs/dbglog'
logfile = '/1/pharos/db/authortest'
logfile = '/1/pharos/db/good'
logfile = '/1/pharos/db/pharos'
# logfile = '/1/pharos/db/crap'

#logfile = '/tmp/log.test'
outfile = sys.stdout
outfile = open('solr1.xml', 'w')
oca_map = open('oca-map.log', 'a')

# tcp socket of solr server
solr = ('localhost', 8983)

from infogami.tdb.logger import parse, parse1, parse2a, parse2b
import infogami.tdb.tdb
import web

import re
import socket
from itertools import *
from itools import *
from cStringIO import StringIO
from operator import itemgetter
from time import time

fst = itemgetter(0)
snd = itemgetter(1)

def setup():
    web.config.db_parameters = dict(dbn="postgres",
#                                    db="pharos",
                                    db="pharos",
                                    user="pharos",
                                    pw="pharos")
    web.load()

def logparse(log_fd):
    return parse2b(parse1(log_fd,
                          infinite=True))

def speed():
    p = logparse(logfile)
    t0=time()
    n = sum(1 for x in p)
    dt = time()-t0
    print '%d items, %.3f seconds, %.2f items/sec'% (n, dt, n/dt)

setup()

# ================================================================

# from exclude import excluded_fields, multivalued_fields
import solr_fields

def main():
    import time as _time

    global t,k
    # out = open('solr.xml', 'w')
    t1 = t0 = time()
    print 'start time: ', _time.ctime(t0)

    log_fd = open(logfile)
    lastpos_fd = open('lastpos', 'r+', 0)
    lastpos = int(open('lastpos').readline())
    print 'seeking to %d'% lastpos
    log_fd.seek(lastpos)

    for i,t in enumerate(logparse(log_fd)):
#        print (t,t.type,type(t.type),t.type.name, type(t.type.name))
        if time()-t1 > 5 or i % 100 == 0:
            print (i, time()-t1, time()-t0)
            sys.stdout.flush()
            t1 = time()

        if t.type.name not in ('delete', 'edition'):
            continue
        if t.type.name == 'delete': action = 'delete'
        else: action = 'add'

        outbuf = StringIO()
        print >>outbuf, "<%s>"% action
        if emit_doc (outbuf, action, t) is None:
            continue
        print >>outbuf, "</%s>"% action

        if 1:
            xml = outbuf.getvalue()
            # print 'xml:(%s)'% xml
            solr_response = solr_submit(xml)
            assert '<result status="0">' in solr_response, solr_response
            # print 'solr response: ((%s))\n'% solr_response

        else:
            outfile.write(outbuf.getvalue())
            outfile.flush()

        lastpos_fd.seek(0)
        log_pos = log_fd.tell()
        lastpos_fd.write('%d\n'% log_pos)
        lastpos_fd.flush()

    lastpos_fd.close()

def sort_canon(s):
    s = s.strip().lower()
    s = re.sub('\s+', ' ', s)
    return s

# dict of fields for which there will be a corresponding sortable
# field.  The field values will have to be transformed into a
# sorting key that does stuff like strips punctuation and folds
# case, or inserts leading zeros for numeric fields,
# but for now we just use the identity function.  The
# dict entries are of the form:
#     fieldname : (new field name, conversion function)

def identity(x): return x

sorted_field_dict = {
#    'authors': ('creatorSorter', sort_canon),
#    'title': ('titleSorter', sort_canon),
    # for publish_date, also output 'date' which basic query
    # treats specially to handle ranges
#    'publish_date': ('date', identity),
    }

ids_seen = set()

def emit_doc(outbuf, action, t, loss=count()):
    assert t.name not in ids_seen, t.name
    for forbidden in ('text', 'identifier'):
        assert forbidden not in t.d
    ids_seen.add(t.name)

    print >>outbuf, "<doc>"

    emit_field(outbuf, 'identifier', t.name)

    if 'oca_identifier' in t.d:
        print >> oca_map, (t.d.oca_identifier, t.name, time())
        oca_map.flush()

    if action != 'delete':
        for k in t.d:
            v = getattr(t.d, k)

            try:
                emit_field(outbuf, k, v)
            except infogami.tdb.tdb.NotFound, e:
                print ('dropping', loss.next(), time(), t.name)
                return None

            if k in solr_fields.singleton_fields:
                # should do something better than crash the importer
                # on finding this error.  but it shouldn't happen. @@
                assert type(v) != list or len(v) == 1, (t,k,v)

            if k not in solr_fields.excluded_fields:
                emit_field(outbuf, 'text', v)
            if k in sorted_field_dict:
                sfname, conversion = sorted_field_dict[k]
                global z                    # debug @@
                z = (t,k,v)
                if type(v) != list:
                    assert type(v) == str
                    v = [v]
                emit_field(outbuf, sfname, map(conversion,map(str,v)))
                       
    print >>outbuf, "</doc>\n"
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

        print >>outbuf, '  <field name="%s">%s</field>'% (field_name,
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
