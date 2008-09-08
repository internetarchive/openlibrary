import web
import simplejson

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
        
class upload:
    def POST(self, category):
        i = web.input('olid', author=None, file={}, source_url=None)

        #@@ downloading from source_url is not yet implemented.
        data = i.file.value
        source_url = None
        
        if not data:
            print 'no image'
            return

        d = {
            'category': category,
            'olid': i.olid,
            'author': i.author,
            'source_url': source_url,
        }
        filename = _disk.write(data, d)
        d['ip'] = web.ctx.ip
        d['filename'] = filename
        print >> web.debug, 'db.new', d
        db.new(**d)
        print "done"
        
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
        i = web.input(id=None)
        id = i.id and safeint(i.id, None)
        if id:
            db.touch(id)
            print 'Done'
        else:
            print 'no such id: %s' % id
