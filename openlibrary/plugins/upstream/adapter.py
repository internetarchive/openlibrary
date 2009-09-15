"""Adapter to provide upstream URL structure over existing Open Library Infobase interface.

Upstream requires:

    /user/.* -> /people/.*
    /b/.* -> /books/.*
    /a/.* -> /authors/.*
    
This adapter module is a filter that sits above an Infobase server and fakes the new URL structure.
"""
import urllib, urllib2
import simplejson
import web

urls = (
    '/([^/]*)/get', 'get',
    '/([^/]*)/things', 'things',
    '/([^/]*)/versions', 'versions',
    '/([^/]*)/new_key', 'new_key',
    '/([^/]*)/save(/.*)', 'save',
    '/.*', 'proxy'
)
app = web.application(urls, globals())

convertions = {
    '/people/': '/user/',
    '/books/': '/b/',
    '/authors/': '/a/'
}

# inverse of convertions
iconversions = dict((v, k) for k, v in convertions.items())

class proxy:
    def delegate(self, *args):
        self.args = args
        self.input = web.input(_method='GET')
        self.path = web.ctx.path
        
        if web.ctx.method in ['POST', 'PUT']:
            self.data = web.data()
        else:
            self.data = None
            
        headers = dict((k[len('HTTP_'):].replace('-', '_').lower(), v) for k, v in web.ctx.environ.items())
        
        self.before_request()
        try:
            server = web.config.infobase_server
            req = urllib2.Request(server + self.path + '?' + urllib.urlencode(self.input), self.data, headers=headers)
            response = urllib2.urlopen(req)
        except urllib2.HTTPError, e:
            response = e
        self.status_code = response.code
        self.status_msg = response.msg
        self.output = response.read()
        
        self.headers = dict(response.headers.items())
        for k in ['transfer-encoding', 'server', 'connection', 'date']:
            self.headers.pop(k, None)
            
        if self.status_code == 200:
            self.after_request()
        else:
            self.process_error()

        web.ctx.status = "%s %s" % (self.status_code, self.status_msg)
        web.ctx.headers = self.headers.items()
        return self.output

    GET = POST = PUT = DELETE = delegate
    
    def before_request(self):
        pass
        
    def after_request(self):
        if self.output:
            d = simplejson.loads(self.output)
            d = unconvert_dict(d)
            self.output = simplejson.dumps(d)
    
    def process_error(self):
        if self.output:
            d = simplejson.loads(self.output)
            if 'key' in d:
                d['key'] = unconvert_key(d['key'])
            self.output = simplejson.dumps(d)

def convert_key(key, mapping=convertions):
    """
        >>> convert_key("/authors/OL1A", {'/authors/': '/a/'})
        '/a/OL1A'
    """
    for new, old in mapping.items():
        if key.startswith(new):
            key2 = old + key[len(new):]
            return key2
    return key
    
def convert_dict(d, mapping=convertions):
    """
        >>> convert_dict({'author': {'key': '/authors/OL1A'}}, {'/authors/': '/a/'})
        {'author': {'key': '/a/OL1A'}}
    """
    if isinstance(d, dict):
        if 'key' in d:
            d['key'] = convert_key(d['key'], mapping)
        for k, v in d.items():
            d[k] = convert_dict(v, mapping)
        return d
    elif isinstance(d, list):
        return [convert_dict(x, mapping) for x in d]
    else:
        return d

def unconvert_key(key):
    return convert_key(key, iconversions)

def unconvert_dict(d):
    return convert_dict(d, iconversions)    
        
class get(proxy):
    def before_request(self):
        i = self.input
        if 'key' in i:
            i.key = convert_key(i.key)
                    
    def after_request(self):
        d = simplejson.loads(self.output)
        d = unconvert_dict(d)
        self.output = simplejson.dumps(d)
        
class things(proxy):
    def before_request(self):
        for k, v in self.input.items():
            self.input[k] = convert_key(v)
            
    def after_request(self):
        if self.output:
            d = simplejson.loads(self.output)

            if self.input.get('details'):
                d = unconvert_dict(d)
            else:
                d = [unconvert_key(key) for key in d]

            self.output = simplejson.dumps(d)
        
class versions(proxy):
    def before_request(self):
        i = self.input
        if 'key' in i:
            i.key = convert_key(i.key)
            
    def after_request(self):
        if self.output:
            d = simplejson.loads(self.output)
            for v in d:
                v['author'] = v['author'] and unconvert_key(v['author'])
                v['key'] = unconvert_key(v['key'])
            self.output = simplejson.dumps(d)
            
class new_key(proxy):
    def after_request(self):
        if self.output:
            d = simplejson.loads(self.output)
            d = unconvert_key(d)
            self.output = simplejson.dumps(d)
            
class save(proxy):
    def before_request(self):
        self.path = '/%s/save%s' % (self.args[0], convert_key(self.args[1]))
        d = simplejson.loads(self.data)
        d = convert_dict(d)
        self.data = simplejson.dumps(d)

class save_many(proxy):
    def before_request(self):
        i = web.input(_method="POST")
        if 'query' in i:
            q = simplejson.loads(i['query'])
            q = convert_dict(q)
            i['query'] = simplejson.dumps(q)
            self.data = urllib.urlencode(i)

if __name__ == '__main__':
    import sys
    web.config.infobase_server = sys.argv[1].rstrip('/')
    
    sys.argv[1:] = sys.argv[2:]
    app.run() 
