"""Simple implementation of infogami site to use in testing.
"""
import datetime
import web
import glob

from infogami.infobase import client, common

key_patterns = {
    'work': '/works/OL%dW',
    'edition': '/books/OL%dM',
    'author': '/authors/OL%dA',
}

class MockSite:
    def __init__(self):
        self.reset()
        
    def reset(self):
        self.docs = {}
        self.changesets = []
        self.index = []
        self.keys = {'work': 0, 'author': 0, 'edition': 0}
        
    def save(self, query, comment=None, action=None, data=None, timestamp=None):
        timestamp = timestamp or datetime.datetime.utcnow()
        
        key = query['key']
        
        if key in self.docs:
            rev = self.docs[key]['revision'] + 1
        else:
            rev = 1
            
        doc = dict(query)
        doc['revision'] = rev
        doc['last_modified'] = {
            "type": "/type/datetime",
            "value": timestamp.isoformat()
        }
        
        self.docs[key] = doc
        
        changes = [{"key": doc['key'], "revision": rev}]
        changeset = self._make_changeset(timestamp=timestamp, kind=action, comment=comment, data=data, changes=changes)
        self.changesets.append(changeset)
        
        self.reindex(doc)
        
    def quicksave(self, key, type="/type/object", **kw):
        """Handy utility to save an object with less code and get the saved object as return value.
        
            foo = mock_site.quicksave("/books/OL1M", "/type/edition", title="Foo")
        """
        query = {
            "key": key,
            "type": {"key": type},
        }
        query.update(kw)
        self.save(query)
        return self.get(key)

    def _make_changeset(self, timestamp, kind, comment, data, changes):
        id = len(self.changesets)
        return {
            "id": id,
            "kind": kind or "update",
            "comment": comment,
            "data": data,
            "changes": changes,
            "timestamp": timestamp.isoformat(),

            "author": None,
            "ip": "127.0.0.1",
            "bot": False
        }
        
    def get(self, key, revision=None):
        data = self.docs.get(key)
        data = data and web.storage(common.parse_query(data))
        return data and client.create_thing(self, key, self._process_dict(data))

    def _process(self, value):
        if isinstance(value, list):
            return [self._process(v) for v in value]
        elif isinstance(value, dict):
            d = {}
            for k, v in value.items():
                d[k] = self._process(v)
            return client.create_thing(self, d.get('key'), d)
        elif isinstance(value, common.Reference):
            return client.create_thing(self, unicode(value), None)
        else:
            return value

    def _process_dict(self, data):
        d = {}
        for k, v in data.items():
            d[k] = self._process(v)
        return d
        
    def get_many(self, keys):
        return [self.get(k) for k in keys if k in self.docs]
    
    def things(self, query):
        limit = query.pop('limit', 100)
        offset = query.pop('offset', 0)
        
        keys = set(self.docs.keys())
        
        for k, v in query.items():
            keys = set(k for k in self.filter_index(self.index, k, v) if k in keys)
            
        keys = sorted(keys)
        return keys[offset:offset+limit]
                    
    def filter_index(self, index, name, value):
        operations = {
            "~": lambda i, value: isinstance(i.value, basestring) and i.value.startswith(web.rstrips(value, "*")),
            "<": lambda i, value: i.value < value,
            ">": lambda i, value: i.value > value,
            "!": lambda i, value: i.value != value,
            "=": lambda i, value: i.value == value,
        }
        pattern = ".*([%s])$" % "".join(operations)
        rx = web.re_compile(pattern)
        m = rx.match(name)
        
        if m: 
            op = m.group(1)
            name = name[:-1]
        else:
            op = "="
            
        f = operations[op]
        for i in index:
            if i.name == name and f(i, value):
                yield i.key
                    
    def compute_index(self, doc):
        key = doc['key']
        index = common.flatten_dict(doc)
        
        for k, v in index:
            # for handling last_modified.value
            if k.endswith(".value"):
                k = web.rstrips(k, ".value")
                
            if k.endswith(".key"):
                yield web.storage(key=key, datatype="ref", name=web.rstrips(k, ".key"), value=v)
            elif isinstance(v, basestring):
                yield web.storage(key=key, datatype="str", name=k, value=v)
            elif isinstance(v, int):
                yield web.storage(key=key, datatype="int", name=k, value=v)
        
    def reindex(self, doc):
        self.index = [i for i in self.index if i.key != doc['key']]
        self.index.extend(self.compute_index(doc))
        
    def _get_backreferences(self, doc):
        return {}
        
    def _load(self, key, revision=None):
        doc = self.get(key, revision=revision)
        data = doc.dict()
        data = web.storage(common.parse_query(data))
        return self._process_dict(data)
        
    def new(self, key, data=None):
        """Creates a new thing in memory.
        """
        data = common.parse_query(data)
        data = self._process_dict(data or {})
        return client.create_thing(self, key, data)

    def new_key(self, type):
        assert type.startswith('/type/')
        t = type[6:]
        self.keys[t] += 1
        return key_patterns[t] % self.keys[t]
        
def pytest_funcarg__mock_site(request):
    """mock_site funcarg.
    
    Creates a mock site, assigns it to web.ctx.site and returns it.
    """
    def read_types():
        for path in glob.glob("openlibrary/plugins/openlibrary/types/*.type"):
            text = open(path).read()
            doc = eval(text, dict(true=True, false=False))
            if isinstance(doc, list):
                for d in doc:
                    yield d
            else:
                yield doc
    
    def setup_models():
        from openlibrary.plugins.upstream import models
        models.setup()

    site = MockSite()

    setup_models()
    for doc in read_types():
        site.save(doc)

    old_ctx = dict(web.ctx)
    web.ctx.clear()
    web.ctx.site = site
    web.ctx.env = web.ctx.environ = web.storage()
    web.ctx.headers = []
    
    def undo():
        web.ctx.clear()
        web.ctx.update(old_ctx)
    
    request.addfinalizer(undo)
    
    return site
