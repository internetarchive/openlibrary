"""Infobase connection middlewares used in Open Library.
"""

class ConnectionMiddleware:
    """Base class for all connection middlewares."""
    def __init__(self, conn):
        self.conn = conn
        
    def get_auth_token(self):
        return self.conn.get_auth_token()

    def set_auth_token(self, token):
        self.conn.set_auth_token(token)
        
    def dispatch():

    def request(self, sitename, path, method='GET', data=None):
        return self.conn.request(sitename, path, method, data)
        
    def get(self, sitename, data):
        return self.conn.request(sitename, '/get', 'GET', data)

    def get_many(self, sitename, data):
        return self.conn.request(sitename, '/get_many', 'GET', data)

    def write(self, sitename, data):
        return self.conn.request(sitename, '/write', 'POST', data)

    def save(self, sitename, path, data):
        return self.conn.request(sitename, path, 'POST', data)

    def save_many(self, sitename, data):
        return self.conn.request(sitename, '/save_many', 'POST', data)


class UpstreamMigrationMiddleware(ConnectionMiddleware):
    """Connection Middleware to handle change of urls during upstream migration. 

    Ideally those changes should happen in the database, but database is too
    slow to do handle such bulk updates. 
    
    This middleware is requied until the data table in the db is updated.
    """
    
    def request(self, sitename, path, method='GET', data=None):
        if path == "/get":
            return self.get(sitename, data)
        elif path

    def _process_key(self, key):
        mapping = (
            "/l/", "/languages/",
            "/a/", "/authors/",
            "/b/", "/books/",
            "/user/", "/people/"
        )
        
        if "/" in key and key.split("/")[1] in ['a', 'b', 'l', 'user']:
            for old, new in web.group(mapping, 2):
                if key.startswith(old):
                    return new + key[len(old):]
        return key
    
    def exists(self, key):
        try:
            d = ConnectionMiddleware.get(self, "openlibrary.org", {"key": key})
            return True
        except client.ClientException, e:
            return False
    
    def _process(self, data):
        if isinstance(data, list):
            return [self._process(d) for d in data]
        elif isinstance(data, dict):
            if 'key' in data:
                data['key'] = self._process_key(data['key'])
            return dict((k, self._process(v)) for k, v in data.iteritems())
        else:
            return data
    
    def get(self, sitename, data):
        # Hack to make the API work even with old keys.
        if web.ctx.get('path') == "/api/get" and 'key' in data:
            data['key'] = self._process_key(data['key'])
            
        response = ConnectionMiddleware.get(self, sitename, data)
        if response:
            data = simplejson.loads(response)
            
            type = data and data.get("type", {}).get("key") 
            
            if type == "/type/work":
                if data.get("authors"):
                    # some record got empty author records because of an error
                    # temporary hack to fix 
                    authors = [a for a in data['authors'] if 'author' in a]
                    if authors != data['authors']
            elif type == "/type/edition":
                # get rid of title_prefix.
                if 'title_prefix' in data:
                    data['title'] = data['title_prefix'] + ' ' + data['title']
                    del data['title_prefix']
            
            response = simplejson.dumps(self._process(data))
        return response
        
    def get_many(self, sitename, data):
        response = ConnectionMiddleware.get_many(self, sitename, data)
        if response:
            data = simplejson.loads(response)
            response = simplejson.dumps(self._process(data))
        return response


    
