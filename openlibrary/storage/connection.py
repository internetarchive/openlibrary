from infogami.infobase import client
import logging
import os
import simplejson
import re
import web

from ..plugins import openlibrary

logger = logging.getLogger("openlibrary.storage")

class Connection(client.Connection):
    """Infobase connection based on storage.
    """
    response_type = "dict"
    
    def __init__(self, storage, itemid_prefix=""):
        client.Connection.__init__(self)
        self.storage = storage
        self.itemid_prefix = itemid_prefix
    
    def request(self, sitename, path, method="GET", data=None):
        
        get_functions = [
            "get", "get_many", "things", 
            "versions", "_recentchanges", 
            "count_editions_by_work", 
            "new_key"
        ]
        
        post_functions = [
            "save_many"
        ]
        
        name = path[1:]
        
        if method == "GET" and name in get_functions:
            f = getattr(self, name)
            return f(sitename, data)
        elif method == "POST" and name in post_functions:
            f = getattr(self, name)
            return f(sitename, data)
        elif path.startswith("/save/"):
            key = web.lstrips(path, "/save")
            return self.save(sitename, key, data)
            
        # elif path == '/write':
        #     return self.write(sitename, data)
        # elif path.startswith('/save/'):
        #     return self.save(sitename, path, data)
        # elif path == '/save_many':
        #     return self.save_many(sitename, data)
        # elif path.startswith("/_store/") and not path.startswith("/_store/_"):
        #     if method == 'GET':
        #         return self.store_get(sitename, path)
        #     elif method == 'PUT':
        #         return self.store_put(sitename, path, data)
        #     elif method == 'DELETE':
        #         return self.store_delete(sitename, path, data)
        # elif path.startswith("/account"):
        #     return self.account_request(sitename, path, method, data)
        else:
            return self.default_request(sitename, path, method, data)
        
    def get(self, sitename, data):
        logger.debug("get %s", data)

        key = data['key']
        # We don't want to store types as items. Read them from repo instead
        if key.startswith("/type/"):
            typename = key.split("/")[-1]
            path = os.path.join(os.path.dirname(openlibrary.__file__), "types", typename + ".type")
            if os.path.exists(path):
                # the type can either be python dict or JSON
                g = {"true": True, "false": False}
                return eval(open(path).read(), g)
        # elif key.startswith("/config/edition"):
        #     path = os.path.join(os.path.dirname(openlibrary.__file__), "pages", "config_edition.page")
        #     if os.path.exists(path):
        #         return eval(open(path).read())
        else:
            itemid = self.key2itemid(key)
            item = itemid and self.storage.find_item(itemid)
            f = item and item.get_file(itemid + ".json")
            if f:
                return simplejson.loads(f.read())
        
        raise client.ClientException("404 not found", "Not Found")
        
    def key2itemid(self, key):
        if re.match("/[^/]*/OL\d+[AMW]", key):
            return self.itemid_prefix + key.split("/")[-1]
        else:
            return key.lstrip("/").replace("/", "--")
        
    def get_many(self, sitename, data):
        keys = simplejson.loads(data['keys'])
        logger.debug("get_many %s", keys)
        return [self.get(k) for k in keys]
    
    def permission(self, sitename, data):
        return {"write": True, "admin": True}
        
    def save(self, sitename, key, data):
        if isinstance(data, dict):
            # save_many calls this method with data as dict
            doc = data
        else:
            doc = simplejson.loads(data)
        
        _comment = doc.pop("_comment", None)
        _action = doc.pop("_action", None)
        _data = doc.pop("_data", None)
        
        itemid = self.key2itemid(key)
        item = self.storage.find_item(itemid, create=True)
        
        f = item.get_file(itemid + ".json")
        f.write(simplejson.dumps(doc))
        return {"key": key, "revision": 1}

    def save_many(self, sitename, data):
        docs = simplejson.loads(data['query'])
        return [self.save(sitename, doc['key'], doc) for doc in docs]
        
    def new_key(self, sitename, data):
        return "/books/OL2M"
        
    def things(self, sitename, data):
        return []
        
    def versions(self, sitename, data):
        q = simplejson.loads(data['query'])
        dummy = {
            "comment": "Test", 
            "author": None, 
            "ip": "127.0.0.1", 
            "created": "2011-10-10T00:00:00", 
            "data": "{}", 
            "key": q['key'], 
            "action": "update", 
            "author_id": None, 
            "changes": simplejson.dumps([{"key": q['key'], "revision": 1}]),
            "id": 1, 
            "machine_comment": None, 
            "revision": 1
        }
        return [dummy]
        
    def _recentchanges(self, sitename, data):
        return []
        
    def count_editions_by_work(self, sitename, data):
        return 0
                
    def default_request(self, sitename, path, method, data):
        self.handle_error(404, "not found")
        
def create_storage(type, **params):
    if type == "local":
        from . import local
        return local.LocalStorage(**params)
    else:
        raise Exception("Unknown storage type %r" % type)

def create_storage_conn(storage_type="local", **params):
    storage = create_storage(storage_type, **params)
    return Connection(storage)

def setup():
    # install the new connection type    
    client._connection_types['storage'] = create_storage_conn