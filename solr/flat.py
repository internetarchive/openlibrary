from __future__ import with_statement
from collections import deque, defaultdict

from itertools import *
from xml.etree import cElementTree as ET
from cStringIO import StringIO
from time import time, ctime
import sys

testfile_name = 'test-in.xml'
testfile_name = 's2.xml'
testfile_name = 'xml/solr1-1185562645.688127.xml'
testfile_name = 'nulls/solr1-1185495311.022886.xml'
testfile_name = 'xml/solr1.xml'

testfile_names = ('xml/solr1-1185562645.688127.xml',
                  'xml/solr1-1185495311.022886.xml')

# () -> [line]
class pstate: pass
pstate = pstate()
pstate.lineno = 0
pstate.empty_docs = 0

def all_lines():
    for filename in testfile_names:
        print ('processing file', filename, ctime())
        with open(filename) as f:
            pstate.filename = filename
            for line in f:
                pstate.lineno += 1
                pstate.pos = f.tell()
                yield line

# () -> [add]   where add is a doc surrounded by add tags
def add_seq():
    lines = all_lines()
    def bates():
        i=0
        for line in lines:
            if line=='<add>\n': i += 1
            yield (i,line)
    for i,d in groupby(bates(), lambda(a,b):a):
        yield imap(lambda(a,b): b, d)
    
# () -> [doc]
def doc_seq():
    for d in add_seq():
        t = ''.join(list(d)[1:-1])
        if not t:
            # we get some occasional empty docs from the original xml dump
            # not sure why.  count how many.
            pstate.empty_docs += 1
        else:
            yield t

# doc -> doc
def fix_doc(d):
    try:
        e = ET.XML(d)
    except SyntaxError, x:
        raise ValueError, (x,d)

    (title,) = (x for x in e.findall('field') if x.get('name')=='title')
    tplx = list(x for x in e.findall('field') if x.get('name')=='title_prefix_len')

    assert len(tplx) <= 1
    tp_len = int(tplx[0]) if tplx else 0
    ts = ET.SubElement(e, 'field')
    ts.set('name', 'titlesort')
    ts.text = title.text[tp_len:]
    if tp_len:
        print (tp_len, title.text)

    # xml_out = '\n'.join(mk_xml())
    xml_out = ET.tostring(e)
    return xml_out

def tf2():
    global d
    d = doc_seq().next()
    fd = fix_doc(d)
    return fd
    
def testfix():
    dt(imap(fix_doc, doc_seq()))

import operator
snd = operator.itemgetter(1)
    
# [doc], int -> [compound doc]
def cc(seq, groupsize=100):
    # generate sequence of compound docs that can be injected
    # into solr

    # emit runs of groupsize elements
    bb = groupby(enumerate(seq), lambda (i,d): i//groupsize)
    for i,d in bb:
        yield '<add>' + \
              '\n\n<!-- #### -->\n\n'.join(b for a,b in d) + \
              '</add>'

def inject():
    solr = ('localhost', 8993)
    t1 = t0 = time()
    groupsize=1000

    for i,xml in enumerate(cc(groupsize)):
        t2 = time()
        print (i*groupsize,len(xml), t2-t1, t2-t0)

        # don't actually post to solr @@
        if 0:
            solr_response = solr_submit(solr, xml)
            assert '<result status="0">' in solr_response, solr_response

        t1=t2
    print ('done',i,t2-t0)
        
import socket
frotz = False                           # debugging cruft @@
def solr_submit(solr, xml):
    global frotz
    """submit an XML document to solr"""
    sock = socket.socket()

    if not frotz:                       # @@
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

class fcat(file):
    def __init__(self, *fseq):
        self.flist = deque(fseq)
        self.blotz = open('blotz.out', 'w')
    def read(self, *n):
        def cs(n=sys.maxint):
            while self.flist and n != 0:
                r = self.flist[0].read(n)
                # print ('cs',self.flist,n,len(r))
                if len(r) == 0:
                    self.flist.popleft()    # this file exhausted
                else:
                    if hasattr(self, 'blotz'):
                        self.blotz.write(r)
                        self.blotz.flush()
                    yield r
                    n -= len(r)
        return ''.join(cs(*n))

a = ET.iterparse(fcat(StringIO('<outer>\n'),
                      open(testfile_name),
                      StringIO('</outer>\n')))

f = fcat(StringIO('<outer>'),
         open(testfile_name),
         StringIO('</outer>\n'))

b = ET.iterparse(open(testfile_name))

from time import time
def dt(it):
    t0 = time()
    # x = sum(1 for i in it)
    for x,y in enumerate(it):
        if x % 5000 == 0:
            print x,time()-t0
            # y.clear()
    t1 = time()-t0
    print x,t1

print ('start non-inject',ctime())
# inject()
print ('done',ctime())

# z1 = ''.join(f.read(16384) for i in (1,2,3,4))[7:]
# z2 = open(testfile_name).read(16384*4-7)
# print z1==z2
print 'b'
# dt(iter(b))
print 'a'
# dt(iter(a))
