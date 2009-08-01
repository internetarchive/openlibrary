import web
import simplejson
import urllib
import os
from cStringIO import StringIO
import Image
import datetime

import db
import config
from utils import safeint, rm_f, random_string, resize_image, ol_things


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
                if len(value) == 13:
                    key = 'isbn_13'
                else:
                    key = 'isbn_10'
            if key == 'oclc':
                key = 'oclc_numbers'
            olids = ol_things(key, value)
            if olids:
                return _query(category, 'olid', olids)
    return None

def write_image(data, prefix):
    path_prefix = find_image_path(prefix)
    try:
        # save original image
        f = open(path_prefix + '.jpg', 'w')
        f.write(data)
        f.close()
        
        img = Image.open(StringIO(data))
        if img.mode != 'RGB':
            img = img.convert('RGB')
    
        for name, size in config.image_sizes.items():
            path = "%s-%s.jpg" % (path_prefix, name)
            resize_image(img, size).save(path)
        return img
    except IOError, e:
        print 'ERROR:', str(e)
        
        # cleanup
        rm_f(prefix + '.jpg')
        rm_f(prefix + '-S.jpg')
        rm_f(prefix + '-M.jpg')
        rm_f(prefix + '-L.jpg')

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

        prefix = i.olid + '-' + random_string(5)
        
        img = write_image(data, prefix)
        if img is None:
            error(ERROR_BAD_IMAGE)

        d = {
            'category': category,
            'olid': i.olid,
            'author': i.author,
            'source_url': source_url,
        }
        d['width'], d['height'] = img.size

        filename = prefix + '.jpg'
        d['ip'] = web.ctx.ip
        d['filename'] = filename
        d['filename_s'] = prefix + '-S.jpg'
        d['filename_m'] = prefix + '-M.jpg'
        d['filename_l'] = prefix + '-L.jpg'
        db.new(**d)
        raise web.seeother(success_url)

def serve_file(path):
    if ':' in path:
        path, offset, size = path.rsplit(':', 2)
        offset = int(offset)
        size = int(size)
        f = open(path)
        f.seek(offset)
        data = f.read(size)
        f.close()
    else:
        f = open(path)
        data = f.read()
        f.close()
    return data

def serve_image(d, size):
    ensure_thumnnail_created(d.id, find_image_path(d.filename))
    if size:
        filename = d['filename_' + size.lower()] or d.filename + "-%s.jpg" % size.upper()
    else:
        filename = d.filename
    path = find_image_path(filename)
    return serve_file(path)
    
def ensure_thumnnail_created(id, path):
    """Temporary hack during migration to make sure thumbnails are created."""
    if ':' in path or os.path.exists(path + '-S.jpg'):
        return

    # original file is not present. Can't create thumbnails.
    if not os.path.exists(path):
        return
        
    prefix = os.path.basename(path)
    assert not prefix.endswith('.jpg')
    
    write_image(open(path).read(), prefix)

    # write_image also writes the original image to a new file. Delete it as we already have the original image.
    os.remove(path + '.jpg')
    db.getdb().update('cover', where='id=$id', vars=locals(),
        filename_s=prefix + '-S.jpg', 
        filename_m=prefix + '-M.jpg', 
        filename_l=prefix + '-L.jpg', 
    )

def find_image_path(filename):
    if ':' in filename: 
        return os.path.join(config.data_root,'items', filename.rsplit('_', 1)[0], filename)
    else:
        return os.path.join(config.data_root, 'localdisk', filename)

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
            return serve_image(d, size)
        elif config.default_image and i.default.lower() != "false" and not i.default.startswith('http://'):
            return serve_file(config.default_image)
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
        i = web.input(olid=None, offset=0, limit=10, callback=None, details="false")
        offset = safeint(i.offset, 0)
        limit = safeint(i.limit, 10)
        details = i.details.lower() == "true"
        
        if limit > 100:
            limit = 100
        result = db.query(category, i.olid, offset=offset, limit=limit)
        if not details:
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
