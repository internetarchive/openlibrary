"""Simple implementation of mock infogami site to use in testing.
"""
import datetime
import web
import glob

from infogami.infobase import client, common, account
from infogami import config

class MockSite:
    def __init__(self):
        self.reset()
        
    def reset(self):
        self.store = MockStore()
        if config.get('infobase') is None:
            config.infobase = {}
            
        config.infobase['secret_key'] = "foobar"
        
        self.account_manager = self.create_account_manager()
        
        self._cache = {}
        self.docs = {}
        self.changesets = []
        self.index = []
        
    def create_account_manager(self):
        # Hack to use the accounts stuff from Infogami
        from infogami.infobase import config as infobase_config
        
        infobase_config.user_root = "/people"
        
        store = web.storage(store=self.store)
        site = web.storage(store=store, save_many=self.save_many)
        return account.AccountManager(site, config.infobase['secret_key'])
        
    def save_many(self, docs, **kw):
        timestamp = kw.pop("timestamp", datetime.datetime.utcnow())
        for doc in docs:
            self.save(doc, timestamp=timestamp)
        
    def save(self, query, comment=None, action=None, data=None, timestamp=None):
        timestamp = timestamp or datetime.datetime.utcnow()
        print >> web.debug, "mock_site.save", query
        
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
        
    def get_user(self):
        return None
        
    def find_user_by_email(self, email):
        return None
        
    def versions(self, q):
        return []
        
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
        
    def register(self, username, displayname, email, password):
        try:
            self.account_manager.register(
                username=username, 
                email=email, 
                password=password, 
                data={"displayname": displayname})
        except common.InfobaseException, e:
            raise ClientException("bad_data", str(e))
            
    def activate_account(self, username):
        try:
            self.account_manager.activate(username=username)
        except common.InfobaseException, e:
            raise ClientException(str(e))
            
    def update_account(self, username, **kw):
        status = self.account_manager.update(username, **kw)
        if status != "ok":
            raise ClientException("bad_data", "Account activation failed.")
    
        
class MockStore(dict):
    def __setitem__(self, key, doc):
        doc['_key'] = key
        dict.__setitem__(self, key, doc)
        
    put = __setitem__
        
    def put_many(self, docs):
        self.update((doc['_key'], doc) for doc in docs)
        
    def _query(self, type=None, name=None, value=None, limit=100, offset=0):
        for doc in dict.values(self):
            if type is not None and doc.get("type", "") != type:
                continue
            if name is not None and doc.get(name) != value:
                continue
            
            yield doc

    def keys(self, **kw):
        return [doc['_key'] for doc in self._query(**kw)]

    def values(self, **kw):
        return [doc for doc in self._query(**kw)]
        
    def items(self, **kw):
        return [(doc["_key"], doc) for doc in self._query(**kw)]
        
        
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