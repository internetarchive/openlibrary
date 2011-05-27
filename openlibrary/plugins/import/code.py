"""Open Library Import API
"""
 
from infogami.plugins.api.code import add_hook
from openlibrary.plugins.openlibrary.code import can_write
from openlibrary.catalog.marc.marc_binary import MarcBinary
from openlibrary.catalog.marc.parse import read_edition
from openlibrary.catalog.add_book import load

import web
import json
import import_opds
from lxml import etree

def parse_meta_headers(edition):
    # parse S3-style http headers
    # we don't yet support augmenting complex fields like author or language
    string_keys = ['title', 'title_prefix', 'description']

    prefix = 'HTTP_X_ARCHIVE_META_'

    for k, v in web.ctx.env.items():
        if k.startswith(prefix):
            meta_key = k[len(prefix):].lower()
            if meta_key in string_keys:
                edition[meta_key] = v

def parse_data(data):
    if -1 != data[:10].find('<?xml'):
        root = etree.fromstring(data)
        print root.tag
        if '{http://www.w3.org/1999/02/22-rdf-syntax-ns#}RDF' == root.tag:
            print 'parsing RDF'
            return None
        elif '{http://www.w3.org/2005/Atom}entry' == root.tag:
            print 'parsing OPDS/Atom'
            edition = import_opds.parse(root)
        else:
            print 'unrecognized XML format'
            return None
        print 'FOO'*10

    else:
        if len(data) != int(data[:5]):
            return json.dumps({'success':False, 'error':'Bad MARC length'})
    
        rec = MarcBinary(data)
        edition = read_edition(rec)
    
    parse_meta_headers(edition)
    
    return edition

class importapi:
    def GET(self):
        i = web.input(recipient='', callback=None, details="false")
 
        web.ctx.headers = []
        if i.get("format") == "json":
            web.header('Content-Type', 'application/json')
        else:
            web.header('Content-Type', 'text/javascript')
 
        if len(i.recipient) == 0:
            i.recipient = 'world'
 
        return '"hello %s"' % i.recipient

    def POST(self):
        web.header('Content-Type', 'application/json')

        if not can_write():
            return json.dumps({'success':False, 'error':'Permission Denied'})

        data = web.data()
       
        edition = parse_data(data)
        print edition
        #call Edward's code here with the edition dict
        if edition:
            reply = load(edition)
            print '-'*80
            print reply
            print '-'*80
            
            #return json.dumps({'success':False, 'error':'Not Yet Implemented'})
            return json.dumps(reply)
        else:
            return json.dumps({'success':False, 'error':'Failed to parse Edition data'})

add_hook("import", importapi)
