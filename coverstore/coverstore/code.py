import web
import simplejson
import urllib
import os

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

def ol_things(key, value):
    query = {
        'type': '/type/edition',
        key: value, 
        'sort': 'last_modified',
        'limit': 10
    }
    try:
        d = dict(query=simplejson.dumps(query))
        result = urllib.urlopen('http://openlibrary.org/api/things?' + urllib.urlencode(d)).read()
        result = simplejson.loads(result)
        olids = result['result']
        return [olid.split('/')[-1] for olid in olids]
    except:
        import traceback
        traceback.print_exc()

        return []
        
def _query(category, key, value):
    if key == 'id':
        return safeint(value)
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

def download(url):
    r = urllib.urlopen(url)
    return r.read()

def urldecode(url):
    """
        >>> urldecode('http://google.com/search?q=bar&x=y')
        ('http://google.com/search', {'q': 'bar', 'x': 'y'})
    """
    base, query = urllib.splitquery(url)
    items = [item.split('=', 1) for item in query.split('&') if '=' in item]
    d = dict((urllib.unquote(k), urllib.unquote_plus(v)) for (k, v) in items)
    return base, d

def changequery(url, **kw):
    """
        >>> changequery('http://google.com/search?q=foo', q='bar', x='y')
        'http://google.com/search?q=bar&x=y'
    """
    base, params = urldecode(url)
    params.update(kw)
    return base + '?' + urllib.urlencode(params)

def is_valid_image(data):
    import Image
    from cStringIO import StringIO
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

        success_url = i.success_url or web.ctx.get('HTTP_REFERRER') or web.ctx.fullpath
        failure_url = i.failure_url or web.ctx.get('HTTP_REFERRER') or web.ctx.fullpath
        def error((code, msg)):
            url = changequery(failure_url, errcode=code, errmsg=msg)
            web.seeother(url)
            raise StopIteration
        
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

def filesize(path):
    try:
        return os.stat(path).st_size
    except:
        return 0


def serve_file(path):
    # when xsendfile is enabled, lighttpd takes X-LIGHTTPD-Send-file header from response and serves that file.
    if os.getenv('XSENDFILE') == 'true':
        web.header('X-LIGHTTPD-Send-file', os.path.abspath(path))
        web.header('Content-Length', filesize(path))
    else:
        print open(path).read()
        
class cover:
    def GET(self, category, key, value, size):
        i = web.input(default="true")
        key = key.lower()
        
        id = _query(category, key, value)
        if id:
            web.header('Content-Type', 'image/jpeg')
            filename = _cache.get_image(id, size)
            if filename:
                serve_file(filename)
        elif config.default_image and i.default.lower() != "false" and not i.default.startswith('http://'):
            serve_file(config.default_image)
        elif i.default.startswith('http://'):
            web.seeother(i.default)
        else:
            web.notfound()
            web.ctx.output = ""

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
                    'created': r.created.isoformat(),
                    'last_modified': r.last_modified.isoformat(),
                    'source_url': r.source_url
                }
            result = [process(r) for r in result]
                        
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

        id = i.id and safeint(i.id, None)
        if id:
            db.touch(id)
            web.seeother(redirect_url)
        else:
            print 'no such id: %s' % id
