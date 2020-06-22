import re
from six.moves import StringIO
import web
import web

import internetarchive as ia
from infogami.utils import delegate
from six.moves.urllib.parse import quote

from infogami.infobase.client import storify
from infogami.utils import delegate
from infogami.utils.view import render, render_template

from openlibrary.utils.isbn import to_isbn_13
from openlibrary.accounts.model import sendmail


class partner_overlaps(delegate.page):
    path = '/partner-with-us'

    def GET(self):
        template = render.partners()
        template.v2 = True
        return template

    def POST(self):
        i = web.input(email='', name='', org='', isbns='', description='',
                      title='', csv={}, debug=False)
        isbns = re.findall('([0-9X]{10,13})',
                           i.isbns.upper() or (i.csv.value) or '')
        item_name = 'test_%s-ol' % quote(i.org.replace(' ', '-')).lower()
        if not ia.get_item(item_name).metadata:
            md = dict(collection='test_collection', noindex="true",
                      contact="i.email", hidden="true", mediatype="collection",
                      title=i.title, uploader="openlibrary@archive.org",
                      description=i.description, show_search_by_availability="true",
                      status="needs_overlap", test="true")
            ia.upload(item_name, {
                'isbns.txt': StringIO('\n'.join([to_isbn_13(isbn) for isbn in isbns
                                                 if to_isbn_13(isbn)]))
                                                
            }, metadata=md)
        msg = render_template("email/new_partner", item_name, i.org,
                              i.email, i.name, len(isbns))
        sendmail(to='chrisfreeland@archive.org', msg=msg, 
                 cc=['mek@archive.org', 'charleshorn@archive.org'])
        template = render.partners(isbns=isbns)
        template.v2 = True
        return template


def setup():
    pass
