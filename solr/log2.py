import sys
from time import time

sys.path.insert(0, "..")
sys.path.insert(0, "../infogami")

logfile = '/1/dbg/import-logs/dbglog'
logfile = '/1/pharos/db/authortest'
logfile = '/1/pharos/db/good'
logfile = '/1/pharos/db/pharos'
logfile = '/x-home/phr/pharos-log'
# logfile = '/1/pharos/db/crap'

#logfile = '/tmp/log.test'
outfile = sys.stdout

outfile = open('solr1-%f.xml' % time(), 'w')
oca_map = open('oca-map.log', 'a')

# tcp socket of solr server
solr = ('localhost', 8993)

from infogami.tdb.logger import parse, parse1, parse2a, parse2b
import infogami.tdb.tdb
import web

import re
import socket
import random, string
from itertools import *
from itools import *
from cStringIO import StringIO
from operator import itemgetter

fst = itemgetter(0)
snd = itemgetter(1)

def setup():
    web.config.db_parameters = dict(dbn="postgres",
#                                    host='apollonius.us.archive.org',
                                    host='localhost',
                                    db="pharos",
                                    user="pharos",
                                    pw="pharos")
    web.load()

# @slicer(20)
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

sys.path.append('../pharos')
import run

import pdb
debug = False

def main():
    if debug:
        pdb.run('main2()')
    else:
        main2()

def main2():
    import time as _time

    global t,k
    # out = open('solr.xml', 'w')
    t1 = t0 = time()
    print 'start time: ', _time.ctime(t0)

    log_fd = open(logfile)
    lastpos_fd = open('lastpos2', 'r+', 0)
    lastpos = int(open('lastpos2').readline())
    print 'seeking to %d'% lastpos
    log_fd.seek(lastpos)

    for i,t in enumerate(logparse(log_fd)):
        # print (t,t.type,type(t.type),t.type.name, type(t.type.name))
        if time()-t1 > 5 or i % 100 == 0:
            print (i, time()-t1, time()-t0)
            sys.stdout.flush()
            t1 = time()

        assert t.type.name.startswith('type/')
        typename = t.type.name[5:]
        assert '/' not in typename

        action = {'delete': 'delete',
                  'edition': 'add'}.get(typename)
        if action is None:
            # this is probably an author record; anyway it's something
            # that we don't index.
            continue

        outbuf = StringIO()
        print >>outbuf, "<%s>"% action
        if emit_doc (outbuf, action, t) is None:
            continue
        print >>outbuf, "</%s>"% action

        if 0:
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

    if t.name in ids_seen:
        # This is not supposed to happen and there was an assertion
        # against it, but it kept triggering so we ignore it for now.
        print ('error', loss.next(), time(), t.name)
        return ''

    for forbidden in ('text', 'identifier'):
        assert forbidden not in t.d
    ids_seen.add(t.name)

    print >>outbuf, "<doc>"

    emit_field(outbuf, 'identifier', t.name)

    # if 'oca_identifier' in t.d:
    #    print >> oca_map, (t.d.oca_identifier, t.name, time())
    #    oca_map.flush()

    if action != 'delete':
        for k in t.d:
            if k == 'authors':
                def translate(a):
                    try:                   return a.d.name
                    except (AttributeError,infogami.tdb.tdb.NotFound), e:
                        id_str = t.d.get('identifier', '(no identifier)')
                        print ('nameless_author', loss.next(), a, id_str, e.args)
                        return a

                v = list(translate(a) for a in getattr(t.d,k))
                # print 'expanded authors (%s)=>(%s)'% (getattr(t.d,k), v)
            else:
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

        # emit a field indicating the availability of fulltext,
        # so we can give it a big scoring bonus at query time.
        if 'oca_identifier' in t.d:
            emit_field(outbuf, 'has_fulltext', '1')
        else:
            emit_field(outbuf, 'has_fulltext', '0')
                       
        # make an xfacet field (random 10-character "word").
        # this is for use in statistical faceting.
        # might want to add more such words or fields, to help make
        # multiple overlapping queries get uncorrelated result sets.
        random_xword = ''.join(random.choice(string.lowercase)
                               for i in xrange(10))
        emit_field(outbuf, 'xfacet', random_xword)

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
    raise ValueError, 'oops'

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
