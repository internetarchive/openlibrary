import web
import simplejson
import urllib
import os
import Image
import datetime
import couchdb

import db
import config
from utils import safeint, rm_f, random_string, ol_things, ol_get, changequery, download

from coverlib import save_image, read_image, read_file

import ratelimit

urls = (
    '/', 'index',
    '/([^ /]*)/upload', 'upload',
    '/([^ /]*)/upload2', 'upload2',    
    '/([^ /]*)/([a-zA-Z]*)/(.*)-([SML]).jpg', 'cover',
    '/([^ /]*)/([a-zA-Z]*)/(.*)().jpg', 'cover',
    '/([^ /]*)/([a-zA-Z]*)/(.*).json', 'cover_details',
    '/([^ /]*)/query', 'query',
    '/([^ /]*)/touch', 'touch',
    '/([^ /]*)/delete', 'delete',
)
app = web.application(urls, locals())

def get_cover_id(olkeys):
    """Return the first cover from the list of ol keys."""
    for olkey in olkeys:
        doc = ol_get(olkey)
        if not doc:
            continue
        
        if doc['key'].startswith("/authors"):
            covers = doc.get('photos', [])
        else:
            covers = doc.get('covers', [])
            
        if covers:
            return covers[0]
            
_couchdb = None
def get_couch_database():
    global _couchdb
    if config.get("couchdb_database"):
        _couchdb = couchdb.Database(config.couchdb_database)
    return _couchdb
    
def find_coverid_from_couch(db, key, value):
    rows = db.view("covers/by_id", key=[key, value], limit=10, stale="ok")
    rows = list(rows)
    
    if rows:
        row = max(rows, key=lambda row: row.value['last_modified'])
        return row.value['cover']

def _query(category, key, value):
    if key == 'olid':
        prefixes = dict(a="/authors/", b="/books/", w="/works/")
        if category in prefixes:
            olkey = prefixes[category] + value
            return get_cover_id([olkey])
    else:
        if category == 'b':
            db = get_couch_database()
            if db:
                return find_coverid_from_couch(db, key, value)
            
            if key == 'isbn':
                if len(value.replace('-', '')) == 13:
                    key = 'isbn_13'
                else:
                    key = 'isbn_10'
            if key == 'oclc':
                key = 'oclc_numbers'
            olkeys = ol_things(key, value)
            return get_cover_id(olkeys)
    return None

ERROR_EMPTY = 1, "No image found"
ERROR_INVALID_URL = 2, "Invalid URL"
ERROR_BAD_IMAGE = 3, "Invalid Image"

class index:
    def GET(self):
        return '<h1>Open Library Book Covers Repository</h1><div>See <a href="http://openlibrary.org/dev/docs/api/covers">Open Library Covers API</a> for details.</div>'

def _cleanup():
    web.ctx.pop("_fieldstorage", None)
    web.ctx.pop("_data", None)
    web.ctx.env = {}
        
class upload:
    def POST(self, category):
        i = web.input('olid', author=None, file={}, source_url=None, success_url=None, failure_url=None)

        success_url = i.success_url or web.ctx.get('HTTP_REFERRER') or '/'
        failure_url = i.failure_url or web.ctx.get('HTTP_REFERRER') or '/'
        
        def error((code, msg)):
            print >> web.debug, "ERROR: upload failed, ", i.olid, code, repr(msg)
            _cleanup()
            url = changequery(failure_url, errcode=code, errmsg=msg)
            raise web.seeother(url)
        
        if i.source_url:
            try:
                data = download(i.source_url)
            except:
                error(ERROR_INVALID_URL)
            source_url = i.source_url
        elif i.file is not None and i.file != {}:
            data = i.file.value
            source_url = None
        else:
            error(ERROR_EMPTY)

        if not data:
            error(ERROR_EMPTY)

        try:
            save_image(data, category=category, olid=i.olid, author=i.author, source_url=i.source_url, ip=web.ctx.ip)
        except ValueError:
            error(ERROR_BAD_IMAGE)

        _cleanup()
        raise web.seeother(success_url)
        
class upload2:
    """Temporary upload handler for handling upstream.openlibrary.org cover upload.
    """
    def POST(self, category):
        i = web.input(olid=None, author=None, data=None, source_url=None, ip=None, _unicode=False)

        web.ctx.pop("_fieldstorage", None)
        web.ctx.pop("_data", None)
        
        def error((code, msg)):
            _cleanup()            
            e = web.badrequest()
            e.data = simplejson.dumps({"code": code, "message": msg})
            raise e
            
        source_url = i.source_url
        data = i.data
            
        if source_url:
            try:
                data = download(source_url)
            except:
                error(ERROR_INVALID_URL)
            
        if not data:
            error(ERROR_EMPTY)

        try:
            d = save_image(data, category=category, olid=i.olid, author=i.author, source_url=i.source_url, ip=i.ip)
        except ValueError:
            error(ERROR_BAD_IMAGE)
        
        _cleanup()
        return simplejson.dumps({"ok": "true", "id": d.id})

def trim_microsecond(date):
    # ignore microseconds
    return datetime.datetime(*date.timetuple()[:6])

class cover:
    def GET(self, category, key, value, size):
        i = web.input(default="true")
        key = key.lower()
        
        def notfound():
            if config.default_image and i.default.lower() != "false" and not i.default.startswith('http://'):
                return read_file(config.default_image)
            elif i.default.startswith('http://'):
                raise web.seeother(i.default)
            else:
                raise web.notfound("")
                
        def redirect(id):
            size_part = size and ("-" + size) or ""
            url = "/%s/id/%s%s.jpg" % (category, id, size_part)
            
            query = web.ctx.env.get('QUERY_STRING')
            if query:
                url += '?' + query
            raise web.found(url)
        
        if key == 'isbn':
            value = value.replace("-", "").strip() # strip hyphens from ISBN
            # Disabling ratelimit as iptables is taking care of botnets.
            #value = self.ratelimit_query(category, key, value)
            value = self.query(category, key, value)
        elif key != 'id':
            value = self.query(category, key, value)
        
        d = value and db.details(value)
        if not d:
            return notfound()

        # set cache-for-ever headers only when requested with ID
        if key == 'id':
            etag = "%s-%s" % (d.id, size.lower())
            if not web.modified(trim_microsecond(d.created), etag=etag):
                raise web.notmodified()

            web.header('Cache-Control', 'public')
            web.expires(100 * 365 * 24 * 3600) # this image is not going to expire in next 100 years.
        else:
            web.header('Cache-Control', 'public')
            web.expires(10*60) # Allow the client to cache the image for 10 mins to avoid further requests
        
        web.header('Content-Type', 'image/jpeg')
        try:
            return read_image(d, size)
        except IOError:
            raise web.notfound()
           
    def query(self, category, key, value):
        return _query(category, key, value)
        
    ratelimit_query = ratelimit.ratelimit()(query)
            
class cover_details:
    def GET(self, category, key, value):
        d = _query(category, key, value)
        
        if key == 'id':
            web.header('Content-Type', 'application/json')
            d = db.details(value)
            if d:
                if isinstance(d['created'], datetime.datetime):
                    d['created'] = d['created'].isoformat()
                    d['last_modified'] = d['last_modified'].isoformat()
                return simplejson.dumps(d)
            else:
                raise web.notfound("")
        else:
            value = _query(category, key, value)
            if value is None:
                return web.notfound("")
            else:
                return web.found("/%s/id/%s.json" % (category, value))
            
class query:
    def GET(self, category):
        i = web.input(olid=None, offset=0, limit=10, callback=None, details="false", cmd=None)
        offset = safeint(i.offset, 0)
        limit = safeint(i.limit, 10)
        details = i.details.lower() == "true"
        
        if limit > 100:
            limit = 100
            
        if i.olid and ',' in i.olid:
            i.olid = i.olid.split(',')
        result = db.query(category, i.olid, offset=offset, limit=limit)
        
        if i.cmd == "ids":
            result = dict((r.olid, r.id) for r in result)
        elif not details:
            result = [r.id for r in result]
        else:
            def process(r):
                return {
                    'id': r.id,
                    'olid': r.olid,
                    'created': r.created.isoformat(),
                    'last_modified': r.last_modified.isoformat(),
                    'source_url': r.source_url,
                    'width': r.width,
                    'height': r.height
                }
            result = [process(r) for r in result]
                        
        json = simplejson.dumps(result)
        web.header('Content-Type', 'text/javascript')
        if i.callback:
            return "%s(%s);" % (i.callback, json)
        else:
           return json
           
class touch:
    def POST(self, category):
        i = web.input(id=None, redirect_url=None)
        redirect_url = i.redirect_url or web.ctx.get('HTTP_REFERRER')

        id = i.id and safeint(i.id, None)
        if id:
            db.touch(id)
            raise web.seeother(redirect_url)
        else:
            return 'no such id: %s' % id

class delete:
    def POST(self, category):
        i = web.input(id=None, redirect_url=None)
        redirect_url = i.redirect_url

        id = i.id and safeint(i.id, None)
        if id:
            db.delete(id)
            if redirect_url:
                raise web.seeother(redirect_url)
            else:
                return 'cover has been deleted successfully.' 
        else:
            return 'no such id: %s' % id
