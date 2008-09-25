"""
Hook to show mark details in Open Library.
"""
from infogami.utils import delegate
from infogami.utils.view import render

import web
import urllib2
from time import time
import os.path
import sys

# add OL root to sys.path
dir = os.path.dirname(__file__)
root = os.path.join(dir, "../../..")
sys.path.append(root)

from catalog.marc.MARC21 import MARC21Record, MARC21HtmlPrint, MARC21Exn

class show_ia(delegate.page):
    path = "/show-marc/ia:(.*)"

    def GET(self, ia):
        filename = ia + "/" + ia + "_meta.xml"

        url = 'http://www.archive.org/download/%s'% filename

        try:        
            record = urllib2.urlopen(url).read(100000)
        except urllib2.HTTPError, e:
            return "ERROR:" + str(e)

        return render.showia(record, filename)

class show_marc(delegate.page):
    path = "/show-marc/(.*):(\d+):(\d+)"
	
    def GET(self, filename, offset, length):
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

        try:
            record = MARC21Record(result)
        except (ValueError,MARC21Exn), e:
            record = None

        return render.showmarc(record, filename, offset, length)
