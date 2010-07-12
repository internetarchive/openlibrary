"""
Hook to show mark details in Open Library.
"""
from infogami.utils import delegate
from infogami.utils.view import render

import web
import urllib2
from time import time
import os.path
import sys, re

class old_show_marc(delegate.page):
    path = "/show-marc/(.*)"

    def GET(self, param):
        raise web.seeother('/show-records/' + param)

class show_ia(delegate.page):
    path = "/show-records/ia:(.*)"

    def GET(self, ia):
        filename = ia + "/" + ia + "_marc.xml"

        url = 'http://www.archive.org/download/%s'% filename

        try:        
            record = urllib2.urlopen(url).read()
        except urllib2.HTTPError, e:
            return "ERROR:" + str(e)

        from openlibrary.catalog.marc import xml_to_html

        try:
            as_html = xml_to_html.html_record(record)
        except:
            as_html = None

        return render.showia(record, filename, as_html)
        
class show_amazon(delegate.page):
    path = "/show-records/amazon:(.*)"
    
    def GET(self, asin):
        return render.showamazon(asin)

re_bad_meta_mrc = re.compile('^([^/]+)_meta\.mrc$')

class show_marc(delegate.page):
    path = "/show-records/(.*):(\d+):(\d+)"
	
    def GET(self, filename, offset, length):
        m = re_bad_meta_mrc.match(filename)
        if m:
            raise web.seeother('/show-records/ia:' + m.group(1))

        offset = int(offset)
        length = int(length)

        #print "record_locator: <code>%s</code><p/><hr>" % locator

        r0, r1 = offset, offset+length-1
        url = 'http://www.archive.org/download/%s'% filename

        assert 0 < length < 100000

        t0 = time()
        ureq = urllib2.Request(url,
                               None,
                               {'Range':'bytes=%d-%d'% (r0, r1)},
                               )

        try:        
            result = urllib2.urlopen(ureq).read(100000)
        except urllib2.HTTPError, e:
            return "ERROR:" + str(e)

        from openlibrary.catalog.marc import html

        try:
            record = html.html_record(result)
        except ValueError:
            record = None

        return render.showmarc(record, filename, offset, length)
