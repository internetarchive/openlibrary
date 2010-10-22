"""Simple implementation of infogami site to use in testing.
"""
import datetime
import web

from infogami.infobase import client, common

class MockSite:
    def __init__(self):
        self.docs = {}
        self.changesets = []
        self.index = []
        
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
        data = web.storage(common.parse_query(data))
        return client.create_thing(self, key, self._process_dict(data))

    def _process(self, value):
        if isinstance(value, list):
            return [self._process(v) for v in value]
        elif isinstance(value, dict):
            d = {}
            for k, v in value.items():
                d[k] = self._process(v)
            return client.create_thing(self, None, d)
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
