"""Open Library Import API
"""

from infogami.plugins.api.code import add_hook
from infogami import config
from openlibrary.plugins.openlibrary.code import can_write
from openlibrary.catalog.marc.marc_binary import MarcBinary
from openlibrary.catalog.marc.marc_xml import MarcXml
from openlibrary.catalog.marc.parse import read_edition
from openlibrary.catalog import add_book
from openlibrary import accounts
from openlibrary import records

#import openlibrary.tasks
from ... import tasks

import web


import base64
import json
import re
import urllib

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
    tasks.upload_via_s3.delay(s3_item_id, filename, data, s3_key, s3_secret)
    #print 'done queuing s3 upload'

    source_url = 'http://www.archive.org/download/%s/%s' % (s3_item_id, filename)
    return source_url

class importapi:
    def GET(self):
        web.header('Content-Type', 'text/plain')
        tasks.add.delay(777, 777)
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
            reply = add_book.load(edition)
            if source_url:
                reply['source_record'] = source_url
            return json.dumps(reply)
        else:
            return json.dumps({'success':False, 'error':'Failed to parse Edition data'})


class ils_search:
    """Search and Import API to use in Koha. 
    
    When a new catalog record is added to Koha, it makes a request with all
    the metadata to find if OL has a matching record. OL returns the OLID of
    the matching record if exists, if not it creates a new record and returns
    the new OLID.
    
    Request Format:
    
        POST /api/ils_search
        Content-type: application/json
        Authorization: Basic base64-of-username:password
    
        {
            'title': '',
            'authors': ['...','...',...]
            'publisher': '...',
            'publish_year': '...',
            'isbn': [...],
            'lccn': [...],
        }
        
    Response Format:
    
        {
            'status': 'found | notfound | created',
            'olid': 'OL12345M',
            'key': '/books/OL12345M',
            'cover': {
                'small': 'http://covers.openlibrary.org/b/12345-S.jpg',
                'medium': 'http://covers.openlibrary.org/b/12345-M.jpg',
                'large': 'http://covers.openlibrary.org/b/12345-L.jpg',
            },
            ...
        }
        
    When authorization header is not provided and match is not found,
    status='notfound' is returned instead of creating a new record.
    """
    def POST(self):
        try:
            rawdata = json.loads(web.data())
        except ValueError,e:
            raise self.error("Unparseable JSON input \n %s"%web.data())

        # step 1: prepare the data
        data = self.prepare_input_data(rawdata)
    
        # step 2: search 
        matches = self.search(data)

        # step 3: Check auth
        try:
            auth_header = http_basic_auth()
            self.login(auth_header)
        except accounts.ClientException:
            raise self.auth_failed("Invalid credentials")

        # step 4: create if logged in
        keys = []
        if auth_header:
            keys = self.create(matches)
        
        # step 4: format the result
        d = self.format_result(matches, auth_header, keys)
        return json.dumps(d)

    def error(self, reason):
        d = json.dumps({ "status" : "error", "reason" : reason})
        return web.HTTPError("400 Bad Request", {"Content-type": "application/json"}, d)


    def auth_failed(self, reason):
        d = json.dumps({ "status" : "error", "reason" : reason})
        return web.HTTPError("401 Authorization Required", {"WWW-Authenticate": 'Basic realm="http://openlibrary.org"', "Content-type": "application/json"}, d)

    def login(self, authstring):
        if not authstring:
            return
        authstring = authstring.replace("Basic ","")
        username, password = base64.decodestring(authstring).split(':')
        accounts.login(username, password)
        
    def prepare_input_data(self, rawdata):
        data = dict(rawdata)
        identifiers = {}
        for i in ["oclc_numbers", "lccn", "ocaid", "isbn"]:
            if i in data:
                identifiers[i] = data.pop(i)
        data['identifiers'] = identifiers

        if "authors" in data:
            authors = data.pop("authors")
            data['authors'] = [{"name" : i} for i in authors]

        return {"doc" : data}
        
    def search(self, params):
        matches = records.search(params)
        return matches

    def create(self, items):
        return records.create(items)
            
    def format_result(self, matches, authenticated, keys):
        doc = matches.pop("doc", {})
        if doc and doc['key']:
            doc = web.ctx.site.get(doc['key']).dict()
            # Sanitise for only information that we want to return.
            for i in ["created", "last_modified", "latest_revision", "type", "revision"]: 
                doc.pop(i)
            # Main status information
            d = {
                'status': 'found',
                'key': doc['key'],
                'olid': doc['key'].split("/")[-1]
            }
            # Cover information
            covers = doc.get('covers') or []
            if covers and covers[0] > 0:
                d['cover'] = {
                    "small": "http://covers.openlibrary.org/b/id/%s-S.jpg" % covers[0],
                    "medium": "http://covers.openlibrary.org/b/id/%s-M.jpg" % covers[0],
                    "large": "http://covers.openlibrary.org/b/id/%s-L.jpg" % covers[0],
                }

            # Pull out identifiers to top level
            identifiers = doc.pop("identifiers",{})
            for i in identifiers:
                d[i] = identifiers[i]
            d.update(doc)

        else:
            if authenticated:
                d = { 'status': 'created' , 'works' : [], 'authors' : [], 'editions': [] }
                for i in keys:
                    if i.startswith('/books'):
                        d['editions'].append(i)
                    if i.startswith('/works'):
                        d['works'].append(i)
                    if i.startswith('/authors'):
                        d['authors'].append(i)
            else:
                d = {
                    'status': 'notfound'
                    }
        return d
        
def http_basic_auth():
    auth = web.ctx.env.get('HTTP_AUTHORIZATION')
    return auth and web.lstrips(auth, "")
        
        
class ils_cover_upload:
    """Cover Upload API for Koha.
    
    Request Format: Following input fields with enctype multipart/form-data
    
        * olid: Key of the edition. e.g. OL12345M
        * file: image file 
        * url: URL to image
        * redirect_url: URL to redirect after upload

        Other headers:
           Authorization: Basic base64-of-username:password
    
    One of file or url can be provided. If the former, the image is
    directly used. If the latter, the image at the URL is fetched and
    used.

    On Success: 
          If redirect URL specified, 
                redirect to redirect_url?status=ok
          else 
                return 
                {
                  "status" : "ok"
                }
    
    On Failure: 
          If redirect URL specified, 
                redirect to redirect_url?status=error&reason=bad+olid
          else 
                return
                {
                  "status" : "error",
                  "reason" : "bad olid"
                }
    """
    def error(self, i, reason):
        if i.redirect_url:
            url = self.build_url(i.redirect_url, status="error", reason=reason)
            return web.seeother(url)
        else:
            d = json.dumps({ "status" : "error", "reason" : reason})
            return web.HTTPError("400 Bad Request", {"Content-type": "application/json"}, d)


    def success(self, i):
        if i.redirect_url:
            url = self.build_url(i.redirect_url, status="ok")
            return web.seeother(url)
        else:
            d = json.dumps({ "status" : "ok" })
            return web.ok(d, {"Content-type": "application/json"})

    def auth_failed(self, reason):
        d = json.dumps({ "status" : "error", "reason" : reason})
        return web.HTTPError("401 Authorization Required", {"WWW-Authenticate": 'Basic realm="http://openlibrary.org"', "Content-type": "application/json"}, d)

    def build_url(self, url, **params):
        if '?' in url:
            return url + "&" + urllib.urlencode(params)    
        else:
            return url + "?" + urllib.urlencode(params)

    def login(self, authstring):
        if not authstring:
            raise self.auth_failed("No credentials provided")
        authstring = authstring.replace("Basic ","")
        username, password = base64.decodestring(authstring).split(':')
        accounts.login(username, password)

    def POST(self):
        i = web.input(olid=None, file={}, redirect_url=None, url="")

        if not i.olid:
            self.error(i, "olid missing")
            
        key = '/books/' + i.olid
        book = web.ctx.site.get(key)
        if not book:
            raise self.error(i, "bad olid")

        try:
            auth_header = http_basic_auth()
            self.login(auth_header)
        except accounts.ClientException:
            raise self.auth_failed("Invalid credentials")

        from openlibrary.plugins.upstream import covers
        add_cover = covers.add_cover()
        
        data = add_cover.upload(key, i)
        coverid = data.get('id')
        
        if coverid:
            add_cover.save(book, coverid)
            raise self.success(i)
        else:
            raise self.error(i, "upload failed")
    

add_hook("import", importapi)
add_hook("ils_search", ils_search)
add_hook("ils_cover_upload", ils_cover_upload)
