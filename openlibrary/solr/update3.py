#!/usr/bin/python
# -*- Python -*-
from __future__ import with_statement

# warning -- this script is in a half-mangled state right now.
# it basically works as described in ../solr-update.py but other
# stuff in it is only partly implemented, or is dregs of half-removed
# stuff that's no longer used, etc.  It is checked into the repo to help
# with populating test solrs, but the code is not currently fit for 
# general consumption.

import infogami
from infogami.infobase.logreader import LogReader,RsyncLogFile, LogFile
from datetime import datetime,date,timedelta
import simplejson as sj
from time import time,ctime,sleep
from itertools import count, imap,islice,chain
import threading
import os,sys,cgi
import socket
import mutate
from Queue import Queue, Empty
import urllib
from traceback import print_exc
import gzip, contextlib
import re
import traceback, pdb
from optparse import OptionParser
import math

last_post_time = time()

def gzopen(*a):
    return contextlib.closing(gzip.open(*a))

# tcp socket of solr server
solr = ('ia311538', 8983)
solr = ('localhost', 8983)
solr = ('h02', 8983)
solr = ('localhost', 8984)
solr = ('ia311530', 8984)               # staging
solr = ('pharosdb-bu', 7983)            # production
solr = ('localhost', 7983)              # laptop
solr = ('ia331511', 7983)               # dev server
del solr                                # get it from command line!

global gg
                        
def logstream_dump(dumpfile, start=0,stop=None):
    t0 = time()
    skip_chunksize = 10000
    if dumpfile.endswith('.gz'):
        xs = gzip.open(dumpfile)
    else:
        xs = open(dumpfile)

    a,b = divmod(start, skip_chunksize)
    nseen = nseen0 = 0
    for i in xrange(a):
        nseen += sum(1 for x in islice(xs, skip_chunksize))
        print ('nseen', nseen, time()-t0)
        if nseen == nseen0:
            break       # input exhausted
        
    nseen += sum(1 for x in islice(xs, start - nseen))
    print ('nseen', nseen, time()-t0)
    def unjson(rec, pat=re.compile(r'\S+\t\S+\t(.*)$')):
        g = pat.match(rec)
        json = g.group(1) if g else rec
        return sj.loads(json)

    # pdb.set_trace()
    return imap(unjson, xs)
        
def logstream_scandump():
    xs = open('../scanrec/scan.dump')
    return imap(sj.loads, xs)
    
def logstream_scanrec():
    """import older scanrec format, not used now.  5/2009"""
    import hack_scans
    for (scanrec,bookrec) in hack_scans.scanrec_stream():
        g = scanrec.get('scan_status')
        if g:
            bookrec['scan_status'] = g
        yield bookrec

def logstream_incr(rsync_source, **delta):
    if not delta: delta = dict(hours=12) # default
    # r = LogReader(RsyncLogFile('ia331526::pharos_0/code/openlibrary/pharos/booklog', 'log'))
    r = LogReader(RsyncLogFile(rsync_source, 'log'))
    d = date.today()-timedelta(**delta)
    print d

    r.skip_till(datetime(d.year, d.month, d.day))
    while True:
        for x in r:
            if type(x) == tuple and x[0]=='error': 
               print ('error', ctime(), x)
            else:
                yield x
        print "hit end of rsync stream, reloading", ctime()
        sleep (30)

# logstream = lambda: logstream_incr(hours=1)

def info(type, value, tb):
    traceback.print_exception(type, value, tb)
    print
    # ... then start the debugger in post-mortem mode
    pdb.pm()

sys.excepthook = info

def main():
    global solr

    # logstream = lambda: logstream_incr(hours=1)
    parser = OptionParser()

    # launch this many parallel processes to index a json dump
    # not implemented, for now
    parser.add_option('-j', '--parallel',
                      action='store',
                      type="int",
                      dest="nthreads",
                      )
    # use this to specify source of json dump, e.g. --dump=books.json
    parser.add_option('--dump',
                      action='store',
                      type="str",
                      dest="dump",
                      )
    # use this to specify source of rsync updates (hostname:dir)
    # don't use this and --dump at the same time
    parser.add_option('--rsync', 
                      action='store',
                      type="str",
                      dest="rsync",
                      )
    # use only in combination with --rsync, to specify when to 
    # start updates.  --days=3 means index all records that have
    # arrived in the past 3 days, etc.  You can use just one
    # of these options.  Maybe this can/should be relaxed.
    parser.add_option('--days',
                      action='store',
                      type="int",
                      dest="days",
                      )
    parser.add_option('--hours',
                      action='store',
                      type="int",
                      dest="hours",
                      )
    parser.add_option('--minutes',
                      action='store',
                      type="int",
                      dest="minutes",
                      )

    parser.add_option('--solr',
                      action='store',
                      type="str",
                      dest="solr",
                      )

    # use with --dump, to post a <optimize/> command after finishing
    # processing the dump.  Optimizing takes 25 minutes or so with
    # current dumps.
    parser.add_option('-O', '--optimize', 
                      action='store_true',
                      dest="optimize",
                      )
    args = ['-j3',
            '--days=3',
            '--rsync=json.dump',
            '--solr=localhost:1234',
            '-O']
    # ps = parser.parse_args(args)[0]
    ps = parser.parse_args(sys.argv)[0]

    class Usage(Exception): pass

    def num_set(*args):
        return len(filter(bool, args))

    try:
        if num_set(ps.rsync, ps.dump) != 1:
            raise Usage, 'use exactly one of --dump and --rsync'

        time_args = dict((k,getattr(ps,k)) \
                         for k in ('days','hours','minutes') \
                         if getattr(ps,k) is not None)
        if ps.rsync:
            if len(time_args) != 1:
                raise Usage, \
                    'for rsync you must specify a duration like days=3'
            else:
                logstream = lambda: \
                              logstream_incr(ps.rsync,
                                             **time_args)
        elif ps.dump:
            if len(time_args) != 0:
                raise Usage, 'use duration arg only for --rsync, not --dump'
            else:
                logstream = lambda: logstream_dump(ps.dump)

        if getattr(ps, 'solr', None):
            g = re.match('([^:]+):(\d+)$', ps.solr)
            if not g:
                raise Usage, \
                    'invalid solr target, use --solr=hostname:portnum'
            host, portstr = g.group(1,2)
            solr = (host, int(portstr)) # set global !!
        else:
            raise Usage, 'you must specify a solr target'
            
    except Usage, msg:
        print 'Usage: %s'% msg
        sys.exit(1)

    main1 (logstream)


def classify_logrec(entry):
    if entry is not None:
        return getattr(entry, 'action', 'book')
    else:
        print (('null entry',))
        return None

def chunk_logrecs(logstream):
    for k,gs in groupby(logstream, classify_logrec):
        for gs1 in iter(lambda: list(islice(gs, 1000)), []):
            yield (k, gs1)

def main2(logstream):
    global gg, non_books
    non_book_entries = 0

    # pdb.set_trace()

    sys.stdout.flush()
    sys.stdout = os.fdopen(1, 'wb', 0)  # autoflush stdout after each write

    solr_queue = Queue(1000)
    logpost = threading.Thread(target=solr_post_thread,
                               args=(solr_queue,))
    logpost.setDaemon(True)
    logpost.start()

    print ('start',ctime())

    for action, chunk in chunk_logrecs(logstream):
        func = getattr(Solr_expand, action)
        if func is not None:
            xchunk = imap(func, chunk)
            if xchunk is not None:
                solr_queue.put(Solr_expand.wrap(action, xchunk))
        
class Solr_expand(object):
    @staticmethod
    def book(rec):
        try:
            return fixup_dict(rec)
        except KeyError, e:
            print 'fixup_dict keyerror', (entry, e, e.args)

    @staticmethod
    def author(rec):
        pass
    @staticmethod
    def delete(rec):
        pass

    @staticmethod
    def wrap(action, xchunk):
        pass

def main1(logstream):
    import pdb
    global gg, non_books
    non_book_entries = 0

    # pdb.set_trace()

    sys.stdout.flush()
    sys.stdout = os.fdopen(1, 'wb', 0)  # autoflush stdout after each write

    print ('start',ctime())

    solr_queue = Queue(1000)
    logpost = threading.Thread(target=solr_post_thread,
                               args=(solr_queue,))
    logpost.setDaemon(True)
    logpost.start()
    
    for entry in logstream():
        if entry is None:
            print (('null entry',))
            continue
        if hasattr(entry,'action'):
            action = entry.action
            if action != 'book':
                if action == 'delete':
                    delrec = deletion_post (entry)
                    print ('delete', delrec)

                    # problem here is that deletions can't be interspersed
                    # with docs in a big <add>.  it has to be a separate post.
                    # sigh.   comment it out for now. @@ !!
                    # solr_queue.put(delrec)
                else:
                    non_book_entries += 1
                    if non_book_entries % 100 == 0:
                        # print '%d non_book_entries'% non_book_entries
                        pass
                continue

        # it's a book, process it
        try:
            book = fixup_dict(entry) # for dump.txt @@
        except KeyError, e:
            print 'fixup_dict keyerror', (entry, e, e.args)
            continue

        if False and 'ocaid' in book:
            fulltext_import(book)
        
        # @@ for development, save book in an external variable
        # and break out of loop
        # print sj.dumps(book,indent=1)   # @@
        gg = book

        # generate XML output
        xml = ''.join(emit1(book))

        # post it to the search engine
        solr_queue.put(xml)

    # the following sleep is to give the solr post thread time to
    # finish whatever it might be doing before exiting the program.
    # this is a kludge and should be replaced by sending a "finish"
    # command through the posting queue and receiving a response. @@
    sleep(300)

def serve_status():
    qch = Queue()

    def service():
        while True:
            a,q = qch.get()
            print ('service',a,q)
            q.put(ctime())

    Thread(target=service).start()


def deletion_post(entry):
    key = entry.data['key'].encode('utf-8')
    return '<delete><identifier>%s</identifier></delete>'% key

# this is the solr posting loop that reads from a queue and posts to
# solr when enough items (currently 1000) have arrived or when nothing
# arrives for long enough (currently 1 minute)
def solr_post_thread(q):

    timeout = 6                         # seconds
    timeout = 60                        # seconds
    chunksize = 1000                    # items
    chunk_num_iter = count().next       # no. of chunks processed

    chunk = []

    # set value used as a boolean flag to remember if there are
    # commits pending, empty=false, nonempty=true.  We use a set
    # for this so it can be updated in the post function without
    # using a global variable.
    commit_flag = set()

    def post():
        global last_post_time

        if len(chunk) == 0:
            print ctime(), '(post empty), commit_flag=', commit_flag
            if len(commit_flag) != 0:
                # we had a timeout with no new docs added, so commit
                # if there is anything pending
                print 'committing...'
                t1 = time()
                solr_submit(solr, '<commit/>')
                print 'committing... done (%.2f sec)'% (time()-t1)
                commit_flag.clear()
            return
        try:
            xml = '<add>\n' + ''.join(chunk) + '</add>\n'
        except UnicodeDecodeError, e:
            print ('UnicodeDecodeError', e, map(type,chunk))
            import pickle
            with open("oops.pickle", 'w') as f:
                pickle.dump(chunk, f)
            pdb.set_trace()
            raise                       # @@ !!
        print 'xml: %d bytes'% len(xml)


        timestamp = '%.2f'% time()

        if 0:
            # debug/tracing output @@
            print 'save frob...'
            with gzopen('frob-%s.gz'% timestamp, 'w') as fo:
                fo.write(xml)
        
        # submit xml to search engine and remember to commit it later
        solr_submit (solr, xml)
        commit_flag.add(1)

        def get_ident(doc):
            g = re.search('<field name="identifier">(/b/OL\d+M)</field>', doc)
            return g.group(1) if g else '(unidentified)'

        print ctime(), '%d: submit %d docs, %d chars, ts=%s, last=(%s)\n'%(
            chunk_num_iter(),
            len(chunk),
            len(xml),
            timestamp,
            get_ident(chunk[-1]) if chunk else '(empty)',
            )
        del chunk[:]
        last_post_time = time()
        
    while True:
        # This collects input docs until a full timeout period
        # (currently 1 minute) goes by with no updates, maybe not
        # a good plan if updates are coming in every 30 sec or so.
        # Instead should use q.get_nowait to collect all available
        # input, then post, then check for more input sleeping for
        # a minute if none.  However, the solr config currently
        # autocommits after 20 minutes of updates with no commits,
        # so we rely on that instead.
        try:
            xml = q.get(True, timeout)
            chunk.append(xml)
            if len(chunk) >= chunksize:
                post()
            elif len(chunk) > 0 and time()-last_post_time > timeout:
                post()

        except Empty:
            post()

class xml_buf(object):
    chunksize = 1000

    def __init__(self, *docs):
        raise NotImplementedError
        self.buf = list(docs)
    def add(self, doc):
        self.buf.append(doc)
        if len(self.buf) >= self.chunksize:
            self.flush()
    def flush(self):
        xml = '<add>\n' + ''.join(self.buf) + '</add>\n'
        # solr_submit (solr, xml)   # @@
        print 'submit %d docs, last=(%s)\n'%(
            len(self.buf),
            self.buf[-1] if self.buf else '(empty)')
        self.buf = []

def solr_submit(solr, xml):
    """submit an XML document to solr"""
    sock = socket.socket()
    c = count().next
    t0s = [time()]
    def d(*msg):
        if msg:
            t1=time()
            print 'x', c(), msg, '(%.2f sec)'%(t1-t0s[0])
            t0s[0] = t1

    d('submitting %d bytes'% len(xml))

    response = None
    try:
        d()
        sock.connect(solr)
        d('connected to', solr)
        sock.sendall('POST /solr/update HTTP/1.1\n')
        d()
        sock.sendall('Host: %s:%d\n'% solr)
        d()
        sock.sendall('Content-type:text/xml; charset=utf-8\n')
        d()
        sock.sendall('Content-Length: %d\n\n'% len(xml))
        d('sent',len(xml),'bytes')
        sock.sendall(xml)
        d('sendall done')

        # kludge patrol: we don't always get back the data in one
        # piece and we can't rely on a timeout (since some updates or
        # commits can be very slow), and actually parsing the return
        # string here to check for completeness would be messy.  So we
        # just get one piece which is usually the whole response, but
        # if it's not enough by checking against an empirically
        # observed byte count, another recv always seems to get the
        # rest.  I've never seen this fail so far, but of course it's
        # pathetic.
        response = sock.recv(10000)
        if len(response) < 105:
            olen = len(response)
            response += sock.recv(10000)
            d('r1 done (%d => %d)'% (olen, len(response)))
        d('response is: (%s)'% response)
    except Exception, e:
        print e.args
    finally:
        d()
        sock.close()
        d()
        return response

def fulltext_import(book, frob=[]):
    # stub @@

    # fulltext index strategy:
    # 1. read and index fulltext from extend('djvu.txt')
    # 2. read pagetext from extend('djvu.xml') and convert to
    #    solrizable docs and index
    # 3. do this in a separate process so that is killed after a
    #    timeout, since retrieving the cluster url's can hang.
    #    urllib and urllib2 don't support timeouts directly and
    #    it's difficult to kill a thread, so use a process and
    #    SIGALRM or a remote kill.

    ocaid = 'jeffersonthomas10lipsrich'

    def extend(suffix):
        return 'http://www.archive.org/download/%s/%s_%s'%(
            ocaid,
            ocaid,
            suffix)

    if not frob:
        mxml = urllib.urlopen(extend('meta.xml')).read()
        print 'read %d bytes of meta xml: (%s)'%(
            len(mxml)
            , mxml)
        frob.append(1)

def fixup_dict(entry):
    # convert the infogami storage object to a regular python dict,
    # for more familiar processing.


    if type(entry) != dict:
        book = dict(entry.data.iteritems())
    else:
        book = entry

    def maybe_del(k):
        if k in book: del book[k]

    # remove a bunch of fields that shouldn't go in the search index
    for k in  ('revision',
               'type',
               'last_modified',
               'isbn_invalid',          # should this be kept? @@
               ):
        maybe_del(k)

    # utility functions
    def attr_from_dlist(book, dlist_name, attr_list):
        """pull a single attribute from a list of dictionaries
        book[dlist_name] is a list of dictionaries
        attr_list is a list of attributes to find in the dictionaries
        in the list.
        book[dlist_name] is then replaced with a list of string values
        found on those attributes.
        """
        
        # the filter below is because there are some lists like [None]
        # in the data.
        dlist = filter(bool, book.get(dlist_name, []))

        def wrap(x):
            # wrap x in a list if it's not already one
            return x if type(x) == list else [x]

        # throw all relevant strings into a set to get rid of duplicates
        xs = set(chain(*(wrap(d.get(a)) for d in dlist for a in attr_list if a in d)))
        if xs:
            # if anything found, convert it to a a list and put it into the book object
            book[dlist_name] = list(xs)
        elif dlist_name in book:
            del book[dlist_name]

    # get rid of all fields whose value is None
    p = list(k for k,v in book.iteritems() if v is None)
    for k in p:
        # print "deleting book['%s']==None"% k
        del book[k]

    # languages field now contains a list of language objects.
    # Just extract the language key.  We convert to the language
    # name on output.  The key should be something like "/1/eng".
    # !! actually since there is a language name field, let's use it.
    # maybe should use key instead, since the name probably burns
    # a little more stored field space, but let's try this for now.
    attr_from_dlist(book, 'languages', ['name'])

    # for book authors, get several name fields per Anand's advice
    attr_from_dlist(book, 'authors', ['personal_name',
                                      'name',
                                      'alternate_names'])

    # run additional mutations from external module
    # some of the ones above here should also be moved there.
    mutate.run_mutations(book)
    return book

# XML conversion
# emit1 :: dict -> seq(XML)
def emit1(book,
          # translation table to turn control characters into spaces
          _translate_ctrl = dict((i,32) for i in xrange(32))
          ):
    def y(name, v):
        try:
            return yprime(name, v)
        except Exception, e:
            print 'y exception',e,e.args
            raise
    def yprime(name, v):
        tv = type(v)
        if tv == dict:
            vt = v.get('type')
            if vt == '/type/datetime':
                # should index this date instead of ignoring it @@
                return ''
            elif vt =='/type/text':
                v = v['value']
                tv = type(v)
            elif vt == '/type/toc_item':
                v = v.get('title')
                tv = type(v)
                if not v:
                    return ''
            elif vt is None and 'key' in v:
                v = v['key']
                tv = type(v)
            elif type(vt)==dict:
                vk = vt.get('key')
                if vk == u'/type/language':
                    v = v.get('name', '')
                elif vk == u'/type/toc_item':
                    v = v.get('title', '')
                else:
                    print ('weird type/d', (name,v),book)
                    return ''
                tv = type(v)
            else:
                print ('weird type', (name,v),book)
                return ''

        if tv == int:
            v = unicode(v)
        elif tv == bool:
            v = unicode(int(v))
        elif tv == str:
            v = unicode(v, 'utf-8')
        elif tv != unicode:
            raise TypeError, (name, v)

        # we've gotten a bunch of records with control characters
        # in some of the fields, so we map those to blanks.
        v = v.translate(_translate_ctrl)

        # print 'y(%r:%r)'%((name,v),(type(name),type(v)))
        return '  <field name="%s">%s</field>\n'% \
               (name.encode('utf-8'),
                cgi.escape(v).encode('utf-8'))

    boost = compute_boost(book)
    if boost != 1.0:
        yield '<doc boost="%.2f">\n'% boost
    else:
        yield '<doc>\n'
    for name, val in book.iteritems():
        if name == 'work_count': continue
        if not val: continue
        if type(val) == list:
            for v in filter(bool, val):
                yield y(name, v)
        else:
            yield y(name, val)
    yield '</doc>\n'

def compute_boost(book):
    # ad hoc boost.  figure out a smarter way to do this.
    boost = 1.0
    work_count = book.get('work_count', 0)
    if work_count > 0:
        boost += math.log(work_count,2)
    if any('wikipedia' in a for a in book.get('authors',[])):
        # author in wikipedia is about like 10 titles
        boost += 3.3            # log2(10)
    return boost

# print fixup_dict(sj.load(open('bogobook.json'))['data'])
# main()
