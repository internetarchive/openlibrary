import web
import simplejson

urls = (
    r'/api/upload', 'upload',
    r'/api/query', 'query',
    r'/api/details/(.*)', 'get',
)

def json_processor(f):
    result = f()
    return simplejson.dumps(result)

app = web.application(urls, globals())
app.add_processor(json_processor)

class upload:
    def POST(self):
        i = web.input("image")
        i.image = File(i.image)
        for k in i.keys():
            if k.startswith('_'):
                del i[k]

        id = store.save(i)
        populate_cache(id, file=i.image)
        return {}

class query:
    def GET(self):
        i = web.input()
        limit = i.pop('limit', 100)
        ids = store.query(i, limit=limit)
        return {'result': ids}

class details:
    def GET(self, id):
        o = store.get(id)

        for k, v in o.items():
            if isinstance(v, File):
                del o[k]

        return o
