"""
Web service to provide book cover images.

Images can be queried using a key and value. 
If there are multiple value, the first one is returned.

some example of urls:
    /isbn/1234567890/small.jpg
    /ltid/1234/medium.jpg
    /olid/1234/large.jpg
"""

import os
import web
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
imagecache = None

def run(disk, cachedir, *middleware):
    global store, cache_dir, imagecache
    store = Store(disk)
    cache_dir = cachedir
    imagecache = ImageCache(cache_dir, store, 30000)
    web.run(urls, globals(), *middleware)
    
render = web.template.render(os.path.join(os.path.dirname(__file__), 'templates/'))

class PIL:
    def thumbnail(self, src_file, dest_file, size):
        """Converts src image to thumnail of specified size."""
        import Image
        image = Image.open(src_file)
        image.thumbnail(size)
        image.save(dest_file)

class ImageMagick:
    def thumbnail(self, src_file, dest_file, size):
        size = '%sx%s' % size
        cmd = 'convert -size %s -thumbnail %s %s %s' % (size, size, src_file, dest_file)
        os.system(cmd)
        
imagelib = PIL()

SIZES = dict(small=(100, 100), medium=(200, 200), large=(400, 400))

class ImageCache:
    def __init__(self, cache_dir, store, cache_size=30000):
        self.cache_dir = cache_dir
        self.image_count = len(os.listdir(cache_dir))
        self.cache_size = cache_size
        self.store = store

    def create_thumbnail(self, id, size):
        imagelib.thumbnail(self.imgpath(id, 'original'), self.imgpath(id, size), SIZES[size])

    def imgpath(self, id, size):
        return '%s/%d-%s.jpg' % (self.cache_dir, id, size)

    def write(self, filename, data):
        f = open(filename, 'w')
        f.write(data)
        f.close()

    def populate_cache(self, id, file=None):
        if os.path.exists(self.imgpath(id, 'small')):
            return
        else:
            if file is None:
                result = self.store.get(id, ['image'])
                if result is None:
                    web.notfound()
                    raise StopIteration

                file = result['image']

            data = file.getdata()
            self.write(self.imgpath(id, 'original'), data)
            self.create_thumbnail(id, 'small')
            self.create_thumbnail(id, 'medium')
            self.create_thumbnail(id, 'large')
            os.remove(self.imgpath(id, 'original'))
            self.image_count += 3
            self.prune_cache()
            
    def prune_cache(self):
        if self.image_count > 2 * self.cache_size:
            files = [os.path.join(self.cache_dir, f) for f in os.listdir(self.cache_dir)]
            files.sort(key=lambda f: os.stat(f).st_atime, reverse=True)
            for f in files[self.cache_size:]:
                os.remove(f)
        
    def get_image(self, id, size):
        self.populate_cache(id)
        return open(self.imgpath(id, size)).read()
        
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
        print imagecache.get_image(int(id), size)
        
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
        imagecache.populate_cache(id, file=i.image)
        return dict(id=id)
