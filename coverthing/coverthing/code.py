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

import imagecache
from store.store import Store, File

urls = (
    r'/', 'index',
    r'/upload', 'uploader',
    r'/([^/]*)/(.*)/(thumbnail|small|medium|large).jpg$', 'image',
    r'/api/query', 'query',
    r'/api/upload', 'upload',
    r'/api/multiple_upload', 'multiple_upload',
    r'/api/get/(.*)', 'get',
)

render = web.template.render(os.path.join(os.path.dirname(__file__), 'templates/'))

store = None

def run(*middleware):
    import config
    global store
    store = Store(config.disk)
    web.run(urls, globals(), *middleware)

def redirect_amazon(isbn, size):
    size_codes = dict(thumbnail='THUMBZZZ', small='TZZZZZZZ', medium='MZZZZZZZ', large='LZZZZZZZ')
    url = 'http://images.amazon.com/images/P/%s.01.%s.jpg' % (isbn, size_codes[size])
    web.seeother(url)

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
        d = store.get(id)
        if 'source' in d and d['source'] == 'amazon':
            redirect_amazon(d.get('isbn', '0'), size)
            raise StopIteration
        else:
            print imagecache.get_image(store, int(id), size)
        
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
        for k in i.keys():
            if k.startswith('_'):
                del i[k]
                
        i.image = File(i.image, 'image/jpeg')
        i.setdefault('source', 'unknown')

        id = store.save(i)
        imagecache.populate_cache(store, id, file=i.image)
        return dict(id=id)

class multiple_upload:
    @jsonify
    def POST(self):
        # allow multiple upload only from localhost
        assert web.ctx.env['REMOTE_ADDR'] == '127.0.0.1'

        i = web.input('data')
        data = simplejson.loads(i.data)
        assert isinstance(data, list)

        for d in data:
            assert len(d) > 1
            path = d['image']
            if not os.exists(path):
                raise Exception, 'file not found: ' + p
            d['image'] = File(lambda: open(p).read(), 'image/jpeg')
        
        ids = store.save_multiple(data)
        return dict(ids=ids)

