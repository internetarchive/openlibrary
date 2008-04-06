#!/usr/bin/python2.5
from __future__ import with_statement
import pdb                              # @@
import re,cgi
from collections import defaultdict
from itertools import *
from itools import *
import os,stat,sys
from xml.etree import cElementTree as ET

from facet_hash import facet_token
token_counts = defaultdict(int)

def mprint(*args):
    print args
    sys.stdout.flush()

class Record(object):
    def __init__(self, buf, dd):
        self.buf = buf                  # [(name, value)]
        self.dd = dd                    # { name : [Int] }
        
global dxml

# @slicer(5)
def alldocs(fp):
    while True:
        buf,dd = parse_doc_xml(fp)
        if len(buf) == 0:
            print ('alldocs done', buf,dd)
            return
        yield (buf, dd)


global desc_flush
desc_flush = 0

def parse_doc_xml(fp):
    global dxml, desc_flush
    dxml = get_doc_xml(fp).decode('utf-8')

    dd = defaultdict(list)
    buf = []

    from traceback import print_exc

    try:
        e = ET.XML(dxml)
    except (Exception,SyntaxError), x:
        print 'syntax error:'
        for i,line in zip(count(1), dxml.split('\n')):
            print '%-3d|%s'% (i,line)
        raise ValueError, (x,dd)
        
    fname = ''
    for i,t in enumerate(e.getiterator('field')):
        if fname == 'description':
            # this gets rid of the current catchall ('text') field
            # if the PRECEDING field was a description.  We used to
            # index descriptions as part of the catchall text and so
            # it's included in the input xml, but it's messing up the
            # search results so we get rid of it here.        
            assert t.get('name') == 'text', t
            assert t.text == ftext, (i, e, fname, t.text, ftext)
            ftext = ''
            desc_flush += 1
        else:
            ftext = t.text if t.text is not None else ''

        fname = t.get('name')
        dd[fname].append((i,ftext))
        buf.append((fname,ftext))

    return (buf, dd)
    
def get_doc_xml(fp):
    for x in fp:
        if x.strip() == '<doc>': break
    else:
        raise StopIteration
    a = [x]
    for x in fp:
        a.append(x)
        if x.strip() == '</doc>': break
    return ''.join(a)

# file -> [([(str,str)], {str:[int,str]})]
# @slicer(20)
def alldocs_old(fp):
    raise AssertionError, "this function is obsolete!!!!"

    nmissing = 0                        # @@
    try:
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
                dd[fname].append((i,fval))

            if 'title' not in dd:
                # need to fix this!!!  Sometimes we don't read a
                # complete record because an xml field is spread across
                # several lines.  For now, we just ignore the docs
                # that lose their titles this way. :-(((  @@
                nmissing += 1
                if nmissing % 500 == 0:
                    mprint ('missing title', nmissing, dd)
            else:
                yield buf,dd
    finally:
        mprint ('missed titles', nmissing)

testfile = 'xml/s2.xml'
testfile = 'xml/solr1.xml'
out_dir = 'barf9'

testfile = '/x-home/phr/my-ol/pharos/pharos/access/access0000.xml'
testfile = 'access_in/b0.xml'
out_dir = 'access_out'

params = {'out_dir': out_dir, 'in_filename': testfile }
def update_params():
    for x in sys.argv:
        v = x.split('=')
        if len(v) == 2:
            a,b = v
            assert re.match('^[a-z_]+$', a)
            params[a] = b

update_params()

bunch_size = 1000

import gzip
from contextlib import closing
def zopen(file, *mode):
    if file.endswith('.gz'):
        return closing(gzip.open(file,*mode))
    return open(file,*mode)

def main2():
    try:
        main1()
    except AssertionError, m:
        print 'assertion error (%s)'%m
        pdb.set_trace()

def main():
    for i,b in enumerate(bunches()):
        with zopen('%s/%05d.xml.gz'% (params['out_dir'], i), 'w') as f:
            f.write('<add>\n')
            for j,x in b:
                map_ (f.write, dump(x))
            f.write('</add>\n')
    mprint ('date fields seen', date_fields_seen)

def bunches():
    for i,p in groupby(enumerate(process()),
                       lambda (i,x): i // bunch_size):
        yield imap(list,p)

# () -> [[str]]
def process():
    from time import time,ctime
    t1 = t0 = time()

    filename = params['in_filename']
    mprint ('start', filename, ctime())
    tf = open(filename)
    tsize = os.stat(filename)[stat.ST_SIZE]
    mprint ('file size', tsize)

    # pdb.set_trace()

    for i,(buf,dd) in enumerate(alldocs(tf)):
        if i % 2500 == 0:
            t2 = time()
            pos = tf.tell()
            mprint ('nrec', i, t2-t1, t2-t0, pos, float(pos)/tsize)
            # mprint ('buf,dd', buf, dd)
            t1=t2
        hack_title(buf, dd)
        hack_date(buf, dd)
        hack_field_aliases(buf, dd)
        tokens = get_facet_tokens(buf, dd)
        buf.append(('facet_tokens', ' '.join(tokens)))
        yield buf

    mprint ('done', i, time()-t0)

field_aliases = (
    ('language_code', 'language'),
    ('subjects', 'subject'),
    )

# [str,str], {str : [int, str]} -> None
# mutate buf, dd
def hack_field_aliases(buf, dd):
    # this is a kludge, it should happen earlier in the process
    def d(f): return dd.get(f, [])
    for src,target in field_aliases:
        ns = sorted(d(src)+d(target), key=lambda(a,b): b)
    # stub: doesn't change anything for now @@

# [str,str], {str : [int, str]} -> None
# mutate buf, should mutate dd too @@
def hack_title(buf, dd):
    title_v = dd.get('title')
    try:
        assert title_v and len(title_v) == 1, (title_v, dd)
    except AssertionError:
        mprint('missing title',title_v,dd)
        raise
        return
    idx,title = title_v[0]
    assert buf[idx][0] == 'title',buf

    tpl_v = dd.get('title_prefix_len')
    if tpl_v:
        assert len(tpl_v) == 1, (title_v,tpl_v)
        try:
            tpl = int(tpl_v[0][1])
        except TypeError, e:
            mprint('tpl_v failure',tpl_v,dd,e.args)
            raise
    else:
        tpl = 0

    title_sort = title[tpl:]
    if tpl:
        pass # mprint ('tpl', title, title_sort)
    assert 'title_sort' not in dd
    buf.append(('titleSorter', title_sort))

date_fields_seen = defaultdict(int)

# [str,str], {str : [int, str]} -> None
# mutate dictionary dd
def hack_date(buf, dd):
    for d,v in dd.iteritems():
        if 'date' in d:
            date_fields_seen[d] += 1
            if d !='publish_date':
                print ('alternate date field', (d, v))
    
    assert 'facet_year' not in dd
    publish_dates = dd.get('publish_date', [])
    assert len(publish_dates) <= 1
    if publish_dates:
        yyyy = re.search(r'\d{4}', publish_dates[0][1])
        apparent_year = int(yyyy.group(0)) if yyyy else 0
        yprint.a('publish_dates',publish_dates, yyyy, apparent_year)
        if yyyy and (1500 < apparent_year < 2010):
            facet_year = facetize_year(apparent_year)
            dd['facet_year'] = [(len(buf), facet_year)]
            buf.append(('facet_year', facet_year))
            py = str(apparent_year)
            dd['publication_year'] = [(len(buf), py)]
            buf.append(('publication_year', py))  # add as stored field to solr @@
            yprint.a('buf-dd', buf, dd)

# String -> String
def facetize_year(yyyy):
    """Convert 4-digit numeric year to the facet string for its
    date range, usually a 20 year period.  The facet strings
    are 2000, 1980, 1960, 1940, 1920, pre1920, and unknown
    >>> print facetize_year(2007)
    2000
    >>> print facetize_year(2000)
    2000
    >>> print facetize_year(1997)
    1980
    >>> print facetize_year(1923)
    1920
    >>> print facetize_year(1920)
    1920
    >>> print facetize_year(1919)
    pre1920
    >>> print facetize_year(5864)  # hebrew calendar year
    unknown
    """
    y = int(yyyy)
    if 1920 <= y <= 2010:
        return '%d' % (y - (y % 20))
    elif y < 1920:
        return 'pre1920'
    else:
        return 'unknown'

# [str,str], {str : [int, str]} -> None
# mutate buf and dd
def hack_isbn(buf, dd):
    isbns = dd.get('ISBN_10', []) + dd.get('ISBN_13', [])
    if isbns:
        ii = ' '.join(isbns)
        dd['publication_year'] = [(len(buf), ii)]
        buf.append(('ISBN', ii))
        
def get_facet_tokens(buf, dd):
    # for each facet field:
    #    generate facet tokens
    # insert tokens into buf

    global token_counts

    # should get facet fields from schema, not put them here. @@
    facet_fields = ('authors',
                    'publisher',
                    'subject',
                    ('subjects', 'subject'),
                    'source',
                    'language',
                    'language_code',
                    'has_fulltext',
                    'facet_year',
                    )
    tokens = []
    for xfield in facet_fields:
        if type(xfield) == tuple:
            field, flabel = xfield
        else:
            field = flabel = xfield
        for idx,v in dd.get(field, []):
            assert buf[idx][0] == field
            token_counts[field] += 1
            tokens.append(facet_token(flabel, v))
    return tokens

class yprint:
    m = 0
    @staticmethod
    def a(*args):
        if yprint.m < 20:
            mprint (yprint.m, args)
        yprint.m += 1
            
# [(str, [str])] -> seq[str]
def dump(buf):
    yield '<doc>\n'
    for name, val in buf:
        if val:
            yield '  <field name="%s">%s</field>\n'% \
                  (name,
                   cgi.escape(val.encode('utf-8')))
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

if __name__ == '__main__':
    import doctest
    # doctest.testmod()
    main()

