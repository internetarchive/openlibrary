#!/usr/bin/python2.5

from __future__ import with_statement
import cgi
import cgitb; cgitb.enable()
from itertools import *
import urllib2
from time import time
import sys,os
import re

from catalog.marc.MARC21 import MARC21Record, MARC21HtmlPrint, MARC21Exn

# open('/tmp/mug','w').write('%f\n'% time())

def main():

    print "Content-type: text/html; charset=utf-8"
    print

    # print >> sys.stderr, 'huh'

    form = cgi.FieldStorage()
    def getval(fieldname, form=form):
        f = form.getfirst(fieldname, "")
        return f
    
    locator = getval ('record')
    if locator:
        (file, offset, length) = locator.split (":")
        offset = int (offset)
        length = int (length)
    else:
        file = getval('file')
        offset = int(getval('offset'))
        length = int(getval('length'))
        locator = "%s:%d:%d" % (file, offset, length)

    print "record_locator: <code>%s</code><p/><hr>" % locator

    r0, r1 = offset, offset+length-1
    url = 'http://www.archive.org/download/%s'% file

    assert 0 < length < 100000
    # regular expression was failing for new sources
    #assert re.match('[\w/_.]+$', file)

    t0 = time()
    ureq = urllib2.Request(url,
                           None,
                           {'Range':'bytes=%d-%d'% (r0, r1)},
                           )

    
    result = urllib2.urlopen(ureq).read(100000)
    # print 'urllib2 got %d bytes (%.3f sec):<p/>'% (len(result), time()-t0)

    rec = None
    try:
        rec = MARC21Record(result)
    except (ValueError,MARC21Exn), e:
        print 'Invalid MARC data %s<p/>'% str(e)

    if rec:
        print '<b>LEADER:</b> <code>%s</code><br/>'% result[:24]
        MARC21HtmlPrint(rec)

    print '<hr><p/>'

    print """In order to retrieve the exact bytes of this MARC record, perform a
    HTTP GET on the url <blockquote><b>%s</b></blockquote> and include the HTTP header"""% url
    print "<pre>&nbsp;&nbsp;&nbsp; Range: bytes=%d-%d</pre>"% (r0, r1)
    print """You will need to do this with a special purpose web client
       such as <a href=http://curl.haxx.se>curl</a>, not a browser.
       The curl command you'd use is:
       <blockquote>
       <code>curl -L -r %d-%d '%s'</code>"""% (r0, r1, url)


main()
