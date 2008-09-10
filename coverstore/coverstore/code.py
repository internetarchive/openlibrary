import web
import simplejson
import urllib

import db
import imagecache
import config

urls = (
    '/([^ /]*)/upload', 'upload',
    '/([^ /]*)/([a-zA-Z]*)/(.*)-([SML]).jpg', 'cover',
    '/([^ /]*)/query', 'query',
    '/([^ /]*)/touch', 'touch',
)

_cache = None
_disk = None

class AppURLopener(urllib.FancyURLopener):
    version = "Mozilla/5.0 (Compatible; coverstore downloader http://covers.openlibrary.org)"

urllib._urlopener = AppURLopener()

def run():
    global _cache
    global _disk
    
    _disk = config.disk
    assert config.disk is not None
    _cache = imagecache.ImageCache(config.cache_dir, _disk)
    web.run(urls, globals())

def safeint(value, default=None):
    """
        >>> safeint('1')
        1
        >>> safeint('x')
        >>> safeint('x', 0)
        0
    """
    try:
        return int(value)
    except:
        return default
        
def _query(category, key, value):
    if key == 'id':
        return safeint(value)
    elif key == 'olid':
        result = db.query(category, value, limit=1)
        return result and result[0] or None
    else:
        return None

def download(url):
    r = urllib.urlopen(url)
    return r.read()

def test_valid_image(data):
    import Image
    from CStringIO import StringIO
    try:
        Image.open(StringIO(data))
    except IOError:
        return False
    return True

ERROR_EMPTY = 1, "No image found"
ERROR_INVALID_URL = 2, "Invalid URL"
ERROR_BAD_IMAGE = 3, "Invalid Image"
        
class upload:
    def POST(self, category):
        i = web.input('olid', author=None, file={}, source_url=None, success_url=None, failure_url=None)

        success_url = i.success_url or web.ctx.get('HTTP_REFERRER')
        failure_url = i.failure_url or web.ctx.get('HTTP_REFERRER')
        def error((code, msg)):
            web.seeother(change_query(failure_url, code=code, msg=msg))
            raise StopIteration
        
        if i.source_url:
            try:
                data = download(i.source_url)
            except:
                error(ERROR_INVALID_URL)
            source_url = i.source_url
        else:
            #@@ downloading from source_url is not yet implemented.
            data = i.file.value
            source_url = None

        if not data:
            error(ERROR_EMPTY)
        elif not is_valid_image(data):
            error(ERROR_BAD_IMAGE)

        d = {
            'category': category,
            'olid': i.olid,
            'author': i.author,
            'source_url': source_url,
        }

        filename = _disk.write(data, d)
        d['ip'] = web.ctx.ip
        d['filename'] = filename
        db.new(**d)
        return web.seeother(success_url)
        
class cover:
    def GET(self, category, key, value, size):
        i = web.input(default="true")
        key = key.lower()
        
        id = _query(category, key, value)
        if id:
            web.header('Content-Type', 'image/jpeg')
            filename = _cache.get_image(id, size)
            if filename:
                print open(filename).read()
        elif config.default_image and i.default.lower() != "false":
            print open(config.default_image).read()
        else:
            web.notfound()
            web.ctx.output = ""

class query:
    def GET(self, category):
        i = web.input(olid='', offset=0, limit=10, callback=None)
        offset = safeint(i.offset, 0)
        limit = safeint(i.limit, 10)
        result = db.query(category, i.olid, offset=offset, limit=limit)
        json = simplejson.dumps(result)
        web.header('Content-Type', 'text/javascript')
        if i.callback:
            print "%s(%s);" % (i.callback, json)
        else:
            print json
        
class touch:
    def POST(self, category):
        i = web.input(id=None, redirect_url=None)
        redirect_url = i.redirect_url or web.ctx.get('HTTP_REFERRER')
        print >> web.debug, 'touch', redirect_url

        id = i.id and safeint(i.id, None)
        if id:
            db.touch(id)
            web.seeother(redirect_url)
        else:
            print 'no such id: %s' % id
