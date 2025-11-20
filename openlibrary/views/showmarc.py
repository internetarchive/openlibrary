"""
Hook to show MARC or other source record details in Open Library.
"""

import re

import requests
import web

from .. import app


class old_show_marc(app.view):
    path = "/show-marc/(.*)"

    def GET(self, param):
        raise web.seeother('/show-records/' + param)


class show_ia(app.view):
    path = "/show-records/ia:(.*)"

    def GET(self, ia):
        error_404 = False
        url = f'https://archive.org/download/{ia}/{ia}_meta.mrc'
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.content
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                error_404 = True
            else:
                return "ERROR:" + str(e)

        if error_404:  # no MARC record
            url = f'https://archive.org/download/{ia}/{ia}_meta.xml'
            try:
                response = requests.get(url)
                response.raise_for_status()
                data = response.content
            except requests.HTTPError as e:
                return "ERROR:" + str(e)
            raise web.seeother('https://archive.org/details/' + ia)

        books = web.ctx.site.things(
            {
                'type': '/type/edition',
                'source_records': 'ia:' + ia,
            }
        ) or web.ctx.site.things(
            {
                'type': '/type/edition',
                'ocaid': ia,
            }
        )

        from openlibrary.catalog.marc import html  # noqa: PLC0415

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

        return app.render_template("showia", ia, record, books)


class show_amazon(app.view):
    path = "/show-records/amazon:(.*)"

    def GET(self, asin):
        return app.render_template("showamazon", asin)


class show_bwb(app.view):
    path = "/show-records/bwb:(.*)"

    def GET(self, isbn):
        return app.render_template("showbwb", isbn)


class show_google_books(app.view):
    path = "/show-records/google_books:(.*)"

    def GET(self, isbn):
        return app.render_template("showgoogle_books", isbn)


re_bad_meta_mrc = re.compile(r'^([^/]+)_meta\.mrc$')


class show_marc(app.view):
    path = r"/show-records/(.*):(\d+):(\d+)"

    def GET(self, filename, offset, length):
        if m := re_bad_meta_mrc.match(filename):
            raise web.seeother('/show-records/ia:' + m.group(1))

        loc = f"marc:{filename}:{offset}:{length}"

        books = web.ctx.site.things(
            {
                'type': '/type/edition',
                'source_records': loc,
            }
        )

        offset = int(offset)
        length = int(length)

        r0, r1 = offset, offset + 100000
        url = 'https://archive.org/download/%s' % filename
        headers = {'Range': 'bytes=%d-%d' % (r0, r1)}

        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            result = response.content[:100000]
        except requests.HTTPError as e:
            return "ERROR:" + str(e)

        if (len_in_rec := int(result[:5])) != length:
            raise web.seeother(
                '/show-records/%s:%d:%d' % (filename, offset, len_in_rec)
            )

        from openlibrary.catalog.marc import html  # noqa: PLC0415

        try:
            record = html.html_record(result[0:length])
        except ValueError:
            record = None

        return app.render_template("showmarc", record, filename, offset, length, books)
