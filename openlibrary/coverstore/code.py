import web
import simplejson
import urllib
import os
import Image
import datetime

import db
import config
from utils import safeint, rm_f, random_string, ol_things, changequery, download

from coverlib import save_image, read_image, read_file

urls = (
    '/', 'index',
    '/([^ /]*)/upload', 'upload',
    '/([^ /]*)/([a-zA-Z]*)/(.*)-([SML]).jpg', 'cover',
    '/([^ /]*)/([a-zA-Z]*)/(.*)().jpg', 'cover',
    '/([^ /]*)/([a-zA-Z]*)/(.*).json', 'cover_details',
    '/([^ /]*)/query', 'query',
    '/([^ /]*)/touch', 'touch',
    '/([^ /]*)/delete', 'delete',
)
app = web.application(urls, locals())

def _query(category, key, value):
    if key == 'id':
        result = db.details(safeint(value))
        return result and result[0] or None
    elif key == 'olid':
        result = db.query(category, value, limit=1)
        return result and result[0] or None
    else:
        if category == 'b' and key in ['isbn', 'lccn', 'oclc', 'ocaid']:
            if key == 'isbn':
                if len(value.replace('-', '')) == 13:
                    key = 'isbn_13'
                else:
                    key = 'isbn_10'
            if key == 'oclc':
                key = 'oclc_numbers'
            olids = ol_things(key, value)
            if olids:
                return _query(category, 'olid', olids)
    return None

ERROR_EMPTY = 1, "No image found"
ERROR_INVALID_URL = 2, "Invalid URL"
ERROR_BAD_IMAGE = 3, "Invalid Image"

class index:
    def GET(self):
        return '<h1>Open Library Book Covers Repository</h1><div>See <a href="http://openlibrary.org/dev/docs/api/covers">Open Library Covers API</a> for details.</div>'
        
class upload:
    def POST(self, category):
        i = web.input('olid', author=None, file={}, source_url=None, success_url=None, failure_url=None)

        success_url = i.success_url or web.ctx.get('HTTP_REFERRER') or '/'
        failure_url = i.failure_url or web.ctx.get('HTTP_REFERRER') or '/'
        def error((code, msg)):
            print >> web.debug, "ERROR: upload failed, ", i.olid, code, repr(msg)
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
        raise web.seeother(success_url)
    
class cover:
    def GET(self, category, key, value, size):
        i = web.input(default="true")
        key = key.lower()
        
        d = _query(category, key, value)
        if d:
            if key == 'id':
                web.lastmodified(d.created)
                web.header('Cache-Control', 'public')
                web.expires(100 * 365 * 24 * 3600) # this image is not going to expire in next 100 years.
                
            web.header('Content-Type', 'image/jpeg')
            return read_image(d, size)
        elif config.default_image and i.default.lower() != "false" and not i.default.startswith('http://'):
            return read_file(config.default_image)
        elif i.default.startswith('http://'):
            raise web.seeother(i.default)
        else:
            raise web.notfound("")
            
class cover_details:
    def GET(self, category, key, value):
        d = _query(category, key, value)
        web.header('Content-Type', 'application/json')
        if d:
            if isinstance(d['created'], datetime.datetime):
                d['created'] = d['created'].isoformat()
                d['last_modified'] = d['last_modified'].isoformat()
            return simplejson.dumps(d)
        else:
            raise web.notfound("")

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
