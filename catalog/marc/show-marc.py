#!/usr/bin/python2.5

import web
import urllib2
from time import time
import re

from MARC21 import MARC21Record, MARC21HtmlPrint, MARC21Exn

class show_marc:
    def GET(self, record, offset, length):
        web.header('Content-Type', 'text/html; charset=utf-8')

        file = locator = record
        offset = int(offset)
        length = int(length)

        print "record_locator: <code>%s</code><p/><hr>" % locator

        r0, r1 = offset, offset+length-1
        url = 'http://www.archive.org/download/%s'% file

        assert 0 < length < 100000

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

if __name__ == "__main__":
    urls = (
        "/show-marc/(.*):(\d+):(\d+)", "show_marc"
    )
    web.run(urls, globals())
