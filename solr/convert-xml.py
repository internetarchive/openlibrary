from __future__ import with_statement
import pdb                              # @@
import re
from collections import defaultdict
from itertools import *
from itools import *

interesting = set(('title',
                   'title_prefix_len',
                   'title_sort',
                   'authors',
                   'publish_date'))

# file -> [([(str,str)], {str:[int,str]})]
# @slicer(20)
def alldocs(fp):
    while True:
        # this relies on being able to ignore some <add> and </add> lines
        for x in fp:
            if x == '<doc>\n':
                break
        else:
            # we never found the beginning of a document, so we're done
            return # sentinel

        dd = defaultdict(list)
        buf = []
        pat = re.compile(r' *\<field name="(.*?)"\>(.*?)\</field\>')
        for i,x in enumerate(fp):
            g = pat.match(x)
            if not g:
                break
            fname, fval = g.groups()
            buf.append((fname, fval))
            if True or fname in interesting:
                dd[fname].append((i,fval))
        yield buf,dd

testfile = 'xml/solr1.xml'
testfile = 'xml/s2.xml'

import os,stat,sys

bunch_size = 1000

def main():
    for i,b in enumerate(bunches()):
        with open('barf/%05d.xml'% i, 'w') as f:
            f.write('<add>\n')
            for j,x in b:
                map_ (f.write, dump(x))
            f.write('</add>\n')


def bunches():
    for i,p in groupby(enumerate(process()),
                       lambda (i,x): i // bunch_size):
        yield imap(list,p)

# () -> [[str]]
def process():
    from time import time,ctime
    t1 = t0 = time()

    print ('start', ctime())
    tf = open(testfile)
    tsize = os.stat(testfile)[stat.ST_SIZE]
    print ('file size', tsize)

    for i,(buf,dd) in enumerate(alldocs(tf)):
        if i % 1000 == 0:
            t2 = time()
            pos = tf.tell()
            print ('nrec', i, t2-t1, t2-t0, pos, float(pos)/tsize)
            # print ('buf,dd', buf, dd)
            t1=t2
        hack_title(buf, dd)
        tokens = get_facet_tokens(buf, dd)
        buf.append(('facet_tokens', ' '.join(tokens)))
        yield buf

    print ('done', i, time()-t0)

# [str,str], {str : [int, str]} -> None
# mutate dictionary dd
def hack_title(buf, dd):
    title_v = dd.get('title')
    assert len(title_v) == 1, title_v
    idx,title = title_v[0]
    assert buf[idx][0] == 'title'

    tpl_v = dd.get('title_prefix_len')
    if tpl_v:
        assert len(tpl_v) == 1, (title_v,tpl_v)
        tpl = int(tpl_v[0])
    else:
        tpl = 0

    title_sort = title[tpl:]
    if tpl:
        print ('tpl', title, title_sort)
    assert 'title_sort' not in dd
    buf.append(('title_sort', title_sort))

def get_facet_tokens(buf, dd):
    # for each facet field:
    #    generate facet tokens
    # insert tokens into buf

    # should get facet fields from schema, not put them here. @@
    facet_fields = ('authors', 'publisher')
    tokens = []
    for field in facet_fields:
        for idx,v in dd.get(field, []):
            assert buf[idx][0] == field
            tokens.append(facet_token(field, v))
    return tokens
    
import string
from hashlib import md5 as mkhash

# choose token length to make collisions unlikely (if there is a
# rare collision once in a while, we tolerate it, it just means
# that users may occasionally see some extra search results.
# don't make it excessively large because the tokens do use index space.
# The probability of a collision is approx.  1 - exp(-k**2 / (2*n)) where
# k = total # of facet tokens (= # of books * avg # of fields)
# n = 26 ** facet_token_length
# so for k = 10**8 and facet_token_length = 12,
# this probability is 1 - exp(-1e16/(2*26**12)) = approx 0.05.
# (That's the prob of EVER getting a collision, not the prob. of
# seeing a collision on any particular query).

facet_token_length = 12

# str, str -> str
def facet_token(field, v):
    token = []
    q = int(mkhash('FT,%s,%s'%(field,v)).hexdigest(), 16)
    for i in xrange(facet_token_length):
        q,r = divmod(q, 26)
        token.append(string.lowercase[r])
    return ''.join(token)

# [(str, [str])] -> seq[str]
def dump(buf):
    yield '<doc>\n'
    for name, val in buf:
        yield '  <field name="%s">%s</field>\n'% (name, val)
    yield '</doc>\n'

def map_(func, seq):
    # call func on each element of seq, in order to perform a
    # side effect.  discard any values returned from func.
    for s in seq:
        func(s)

import socket
frotz = False
def solr_submit(solr, xml):
    global frotz
    """submit an XML document to solr"""
    sock = socket.socket()

    if not frotz:
        frotz = True
        with open('frotz','w') as f:
            f.write(xml)
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
