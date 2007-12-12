"""
Web service to provide book cover images.

Images can be queried using a key and value. 
If there are multiple value, the first one is returned.

some example of urls:
    /isbn/1234567890/small.jpg
    /ltid/1234/medium.jpg
    /olid/1234/large.jpg
"""

import os.path
import web
import Image
import simplejson

from store.store import Store, File
urls = (
    r'/', 'index',
    r'/upload', 'uploader',
    r'/([^/]*)/(.*)/(small|medium|large).jpg$', 'image',
    r'/api/query', 'query',
    r'/api/upload', 'upload',
    r'/api/get/(.*)', 'get',
)

store = None
cache_dir = None

def run(disk, cachedir, *middleware):
    global store, cache_dir
    store = Store(disk)
    cache_dir = cachedir
    web.run(urls, globals(), *middleware)
    
render = web.template.render(os.path.join(os.path.dirname(__file__), 'templates/'))

def imgpath(id, size):
    return '%s/%d-%s.jpg' % (cache_dir, id, size)

def write(filename, data):
    print >> web.debug, 'write', filename
    f = open(filename, 'w')
    f.write(data)
    f.close()

SIZES = dict(small=(100, 100), medium=(200, 200), large=(400, 400))

def _convert_thumbnail(src_file, dest_file, sizename):
    """Converts src image to thumnail of specified size."""
    size = SIZES[sizename]
    image = Image.open(src_file)
    image.thumbnail(size)
    image.save(dest_file)

def create_thumbnail(id, size):
    _convert_thumbnail(imgpath(id, 'original'), imgpath(id, size), size)

def populate_cache(id, file=None):
    if os.path.exists(imgpath(id, 'small')):
        return
    else:
        if file is None:
            result = store.get(id, ['image'])
            if result is None:
                web.notfound()
                raise StopIteration

            file = result['image']

        data = file.getdata()
        write(imgpath(id, 'original'), data)
        create_thumbnail(id, 'small')
        create_thumbnail(id, 'medium')
        create_thumbnail(id, 'large')
        
def get_image(id, size):
    populate_cache(id)
    return open(imgpath(id, size)).read()

class index:
    def GET(self):
        print render.index()

class image:
    def GET(self, key, value, size):
        if key == 'id':
            id = value
        else: 
            q = {key: value}
            ids = store.query(q)
            if not ids:
                web.notfound()
                raise StopIteration
            else:
                id = ids[0]
        print get_image(int(id), size)
        
class uploader:
    def GET(self):
        print render.upload()
        
def jsonify(f):
    def g(*a):
        try:
            result = f(*a)
            result['status'] = 'ok'
        except Exception, e:
            import traceback
            traceback.print_exc()
            result = dict(status='fail', message=str(e))
            
        print simplejson.dumps(result)
    return g

class query:
    @jsonify
    def GET(self):
        i = web.input()
        limit = i.pop('limit', 100)
        ids = store.query(i, limit=limit)
        return dict(result=ids)

class get:
    @jsonify
    def GET(self, id):
        o = store.get(id)

        for k, v in o.items():
            if isinstance(v, File):
                del o[k]

        return dict(id=id, properties=o)
        
class upload:
    @jsonify
    def POST(self):
        i = web.input("image")
        i.image = File(i.image)
        for k in i.keys():
            if k.startswith('_'):
                del i[k]

        i.setdefault('source', 'unknown')

        id = store.save(i)
        populate_cache(id, file=i.image)
        return dict(id=id)
