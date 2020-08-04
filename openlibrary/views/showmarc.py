"""
Hook to show MARC or other source record details in Open Library.
"""
from .. import app

import web
import re
import requests


class old_show_marc(app.view):
    path = "/show-marc/(.*)"

    def GET(self, param):
        raise web.seeother('/show-records/' + param)

class show_ia(app.view):
    path = "/show-records/ia:(.*)"

    def GET(self, ia):
        error_404 = False
        url = 'http://www.archive.org/download/%s/%s_meta.mrc' % (ia, ia)
        
        response = requests.get(url)
        
        if not response.ok:
            if response.status_code == 404:
                error_404 = True
            else:
                try:
                    response.raise_for_status()
                except requests.exceptions.HTTPError as e:
                    return "ERROR:" + str(e)
        else:
            data = response.content
        
        if error_404: # no MARC record
            url = 'http://www.archive.org/download/%s/%s_meta.xml' % (ia, ia)
            response = requests.get(url)
            if not response.ok:
                try:
                    response.raise_for_status()
                except requests.exceptions.HTTPError as e:
                    return "ERROR:" + str(e)
            data = response.content
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

        template = app.render_template("showia", ia, record, books)
        template.v2 = True
        return template


class show_amazon(app.view):
    path = "/show-records/amazon:(.*)"

    def GET(self, asin):
        template = app.render_template("showamazon", asin)
        template.v2 = True
        return template


class show_bwb(app.view):
    path = "/show-records/bwb:(.*)"

    def GET(self, isbn):
        template = app.render_template("showbwb", isbn)
        template.v2 = True
        return template


re_bad_meta_mrc = re.compile('^([^/]+)_meta\.mrc$')
re_lc_sanfranpl = re.compile('^sanfranpl(\d+)/sanfranpl(\d+)\.out')

class show_marc(app.view):
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

        response = requests.get(url, headers={'Range':'bytes=%d-%d'% (r0, r1)})
        
        if not response.ok:
            try:
                response.raise_for_status()
            except requests.exceptions.HTTPError as e:
                return "ERROR:" + str(e)
            
        it = response.iter_content(100000)
        done = False
        result = b''
        for chunk in it:
            if done:
                break
            result += chunk
            done = True

        len_in_rec = int(result[:5])
        if len_in_rec != length:
            raise web.seeother('/show-records/%s:%d:%d' % (filename, offset, len_in_rec))

        from openlibrary.catalog.marc import html

        try:
            record = html.html_record(result[0:length])
        except ValueError:
            record = None

        template = app.render_template("showmarc", record, filename, offset, length, books)
        template.v2 = True
        return template
