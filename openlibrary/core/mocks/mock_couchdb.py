"""Library to mock python couchdb library.
"""
import uuid
from couchdb.client import View

class Database:
    def __init__(self):
        self.docs = {}
        self._views = {}
        
        self._views["_all_docs"] = _View(self._map_all_docs)
        
    def _map_all_docs(self, doc):
        yield doc['_id'], {"rev": doc['_rev']}
            
    def compact(self, ddoc=None):
        return True
        
    def save(self, doc, **options):
        doc = dict(doc)
        
        self._add_rev(doc)
        self.docs[doc['_id']] = doc
        
        for view in self._views.values():
            view.add_doc(doc)
            
        if doc['_id'].startswith("_design/"):
            self._process_design_doc(doc)
        
        return (doc['_id'], doc['_rev'])
        
    def _process_design_doc(self, doc):
        id = doc['_id']
        
        # remove old views
        self._views = dict((k, v) for k, v in self._views.items() if not k.startswith(id + "/"))
        
        for name, d in doc.get('views', {}).items():
            viewname = id.split("/")[1] + "/" + name
            if "map" in d:
                map = self._compile(d['map'])
                
                view = _View(map)
                for doc in self.docs.values():
                    view.add_doc(doc)
                
                self._views[viewname] = view
        
    def _compile(self, code):
        globals_ = {}
        _log = lambda *a: None
        
        exec code in {'log': _log}, globals_
        
        err = {'error': {
            'id': 'map_compilation_error',
            'reason': 'string must eval to a function '
                      '(ex: "def(doc): return 1")'
        }}
        if len(globals_) != 1:
            return err
        
        return globals_.values()[0]
        
    def __getitem__(self, key):
        return dict(self.docs[key])
    
    def __setitem__(self, key, doc):
        doc['_id'] = key
        self.save(doc)
        
    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default
        
    def update(self, docs):
        for doc in docs:
            self.save(doc)
                
    def view(self, name, wrapper=None, **options):
        rows = self._views[name].get_rows()
        view = MockView(self, rows, wrapper)
        return view(**options)
    
    def _view(self, name):
        if name == "_all_docs":
            rows = [{"id": doc["_id"], "key": doc["_id"], "value": {"rev": doc["_rev"]}} for doc in docs]
            rows.sort(key=lambda row: row['key'])
            return rows
    
    def _ensure_id(self, doc):
        if '_id' not in doc:
            doc['_id'] = self._uuid()
        return doc
    
    def _uuid(self):
        return str(uuid.uuid1().replace("-", ""))
    
    def _add_rev(self, doc):
        self._ensure_id(doc)
        
        if '_rev' in doc:
            rev = int(doc['_rev']) + 1
        else:
            rev = 1
        doc['_rev'] = str(rev)
        return doc

class _View:
    def __init__(self, map):
        self.map = map
        self.rows = []        
        
    def add_doc(self, doc):
        id = doc['_id']
        self.rows = [row for row in self.rows if row['id'] != id]
        self.rows += [{"id": id, "key": key, "value": value} for key, value in self.map(doc)]
        
    def get_rows(self):
        return sorted(self.rows, key=lambda row: row['key'])
            
class MockView(View):
    def __init__(self, db, rows, wrapper):
        self.db = db
        self.wrapper = wrapper
        self.rows = rows
    
    def _exec(self, options):
        offset = 0
        rows = self.rows[:]
        
        if "key" in options:
            key = options['key']
            try:
                keys = [row['key'] for row in rows]
                offset = keys.index(key)
            except ValueError:
                offset = len(keys)
            rows = [row for row in self.rows if row['key'] == key]
            
        if options.get("include_docs") == True:
            for row in rows:
                row["doc"] = self.db[row['id']]
            
        return {
            "total_rows": len(self.rows),
            "offset": offset,
            "rows": rows,
        }