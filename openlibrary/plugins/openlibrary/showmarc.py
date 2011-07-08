"""
Hook to show mark details in Open Library.
"""
from infogami.utils import delegate
from infogami.utils.view import render

import web
import urllib2
import os.path
import sys, re

class old_show_marc(delegate.page):
    path = "/show-marc/(.*)"

    def GET(self, param):
        raise web.seeother('/show-records/' + param)

class show_ia(delegate.page):
    path = "/show-records/ia:(.*)"

    def GET(self, ia):
        error_404 = False
        url = 'http://www.archive.org/download/%s/%s_meta.mrc' % (ia, ia)
        try:
            data = urllib2.urlopen(url).read()
        except urllib2.HTTPError, e:
            if e.code == 404:
                error_404 = True
            else:
                return "ERROR:" + str(e)

        if error_404: # no MARC record
            url = 'http://www.archive.org/download/%s/%s_meta.xml' % (ia, ia)
            try:
                data = urllib2.urlopen(url).read()
            except urllib2.HTTPError, e:
                return "ERROR:" + str(e)
            raise web.seeother('http://www.archive.org/details/' + ia)

        books = web.ctx.site.things({
            'type': '/type/edition',
            'source_records': 'ia:' + ia,
        }) or web.ctx.site.things({
            'type': '/type/edition',
            'ocaid': ia,
        })

        from openlibrary.catalog.marc import html

        try:
            leader_len = int(data[:5])
        except ValueError:
            return "ERROR reading MARC for " + ia

        if len(data) != leader_len:
            data = data.decode('utf-8').encode('raw_unicode_escape')
        assert len(data) == int(data[:5])

        try:
            record = html.html_record(data)
        except ValueError:
            record = None

        return render.showia(ia, record, books)
        
class show_amazon(delegate.page):
    path = "/show-records/amazon:(.*)"
    
    def GET(self, asin):
        return render.showamazon(asin)

re_bad_meta_mrc = re.compile('^([^/]+)_meta\.mrc$')
re_lc_sanfranpl = re.compile('^sanfranpl(\d+)/sanfranpl(\d+)\.out')

class show_marc(delegate.page):
    path = "/show-records/(.*):(\d+):(\d+)"
	
    def GET(self, filename, offset, length):
        m = re_bad_meta_mrc.match(filename)
        if m:
            raise web.seeother('/show-records/ia:' + m.group(1))
        m = re_lc_sanfranpl.match(filename)
        if m: # archive.org is case-sensative
            mixed_case = 'SanFranPL%s/SanFranPL%s.out:%s:%s' % (m.group(1), m.group(2), offset, length)
            raise web.seeother('/show-records/' + mixed_case)
        if filename == 'collingswoodlibrarymarcdump10-27-2008/collingswood.out':
            loc = 'CollingswoodLibraryMarcDump10-27-2008/Collingswood.out:%s:%s' % (offset, length)
            raise web.seeother('/show-records/' + loc)

        loc = ':'.join(['marc', filename, offset, length])

        books = web.ctx.site.things({
            'type': '/type/edition',
            'source_records': loc,
        })

        offset = int(offset)
        length = int(length)

        #print "record_locator: <code>%s</code><p/><hr>" % locator

        r0, r1 = offset, offset+100000
        url = 'http://www.archive.org/download/%s'% filename

        ureq = urllib2.Request(url,
                               None,
                               {'Range':'bytes=%d-%d'% (r0, r1)},
                               )

        try:        
            result = urllib2.urlopen(ureq).read(100000)
        except urllib2.HTTPError, e:
            return "ERROR:" + str(e)

        len_in_rec = int(result[:5])
        if len_in_rec != length:
            raise web.seeother('/show-records/%s:%d:%d' % (filename, offset, len_in_rec))

        from openlibrary.catalog.marc import html

        try:
            record = html.html_record(result[0:length])
        except ValueError:
            record = None

        return render.showmarc(record, filename, offset, length, books)
