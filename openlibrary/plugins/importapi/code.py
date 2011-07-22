"""Open Library Import API
"""
 
from infogami.plugins.api.code import add_hook
from infogami import config
from openlibrary.plugins.openlibrary.code import can_write
from openlibrary.catalog.marc.marc_binary import MarcBinary
from openlibrary.catalog.marc.marc_xml import MarcXml
from openlibrary.catalog.marc.parse import read_edition
from openlibrary.catalog.add_book import load
import openlibrary.tasks

import web
import json
import re
import import_opds
import import_rdf
import import_edition_builder
from lxml import etree

def parse_meta_headers(edition_builder):
    # parse S3-style http headers
    # we don't yet support augmenting complex fields like author or language
    # string_keys = ['title', 'title_prefix', 'description']

    re_meta = re.compile('HTTP_X_ARCHIVE_META(?:\d{2})?_(.*)')
    for k, v in web.ctx.env.items():
        m = re_meta.match(k)
        if m:
            meta_key = m.group(1).lower()
            edition_builder.add(meta_key, v, restrict_keys=False)


def parse_data(data):
    data = data.strip()
    if -1 != data[:10].find('<?xml'):
        root = etree.fromstring(data)
        #print root.tag
        if '{http://www.w3.org/1999/02/22-rdf-syntax-ns#}RDF' == root.tag:
            edition_builder = import_rdf.parse(root)
            format = 'rdf'
        elif '{http://www.w3.org/2005/Atom}entry' == root.tag:
            edition_builder = import_opds.parse(root)
            format = 'opds'
        elif '{http://www.loc.gov/MARC21/slim}record' == root.tag:
            if root.tag == '{http://www.loc.gov/MARC21/slim}collection':
                root = root[0]
            rec = MarcXml(root)
            edition = read_edition(rec)
            edition_builder = import_edition_builder.import_edition_builder(init_dict=edition)
            format = 'marcxml'
        else:
            print 'unrecognized XML format'
            return None, None
    elif data.startswith('{') and data.endswith('}'):
        obj = json.loads(data)
        edition_builder = import_edition_builder.import_edition_builder(init_dict=obj)
        format = 'json'
    else:
        #Marc Binary
        if len(data) != int(data[:5]):
            return json.dumps({'success':False, 'error':'Bad MARC length'})
    
        rec = MarcBinary(data)
        edition = read_edition(rec)
        edition_builder = import_edition_builder.import_edition_builder(init_dict=edition)
        format = 'marc'

    parse_meta_headers(edition_builder)
    
    return edition_builder.get_dict(), format

def get_next_count():
    store = web.ctx.site.store
    counter = store.get('import_api_s3_counter')
    print 'counter: ',
    print counter
    if None == counter:
        store['import_api_s3_counter'] = {'count':0}
        return 0
    else:
        count = counter['count'] + 1
        store['import_api_s3_counter'] = {'count':count, '_rev':counter['_rev']}
        return count

def queue_s3_upload(data, format):
    s3_key = config.plugin_importapi.get('s3_key')
    s3_secret = config.plugin_importapi.get('s3_secret')
    counter = get_next_count()
    filename = '%03d.%s' % (counter, format)
    s3_item_id = config.plugin_importapi.get('s3_item', 'test_ol_import')
    s3_item_id += '_%03d' % (counter/1000)

    #print 'attempting to queue s3 upload with %s:%s file=%s item=%s' % (s3_key, s3_secret, filename, s3_item_id)
    openlibrary.tasks.upload_via_s3.delay(s3_item_id, filename, data, s3_key, s3_secret)
    #print 'done queuing s3 upload'

    source_url = 'http://www.archive.org/download/%s/%s' % (s3_item_id, filename)
    return source_url

class importapi:
    def GET(self):
        web.header('Content-Type', 'text/plain')
        openlibrary.tasks.add.delay(777, 777)
        return 'Import API only supports POST requests.'

    def POST(self):
        web.header('Content-Type', 'application/json')

        if not can_write():
            return json.dumps({'success':False, 'error':'Permission Denied'})

        data = web.data()
       
        edition, format = parse_data(data)
        #print edition

        source_url = None
        if 'source_records' not in edition:
            source_url = queue_s3_upload(data, format)
            edition['source_records'] = [source_url]

        #call Edward's code here with the edition dict
        if edition:
            reply = load(edition)
            if source_url:
                reply['source_record'] = source_url
            return json.dumps(reply)
        else:
            return json.dumps({'success':False, 'error':'Failed to parse Edition data'})

add_hook("import", importapi)
