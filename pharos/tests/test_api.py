import ol

import web
import simplejson
import urllib, urllib2
import re

class OLError(Exception):
    def __init__(self, http_error):
        self.headers = http_error.headers
        msg = http_error.msg + ": " + http_error.read()
        Exception.__init__(self, msg)

class OpenLibrary:
    def __init__(self, browser):
        self.browser = browser
        self.cookie = None

    def _request(self, path, method='GET', data=None, headers=None):
        url = "http://0.0.0.0:8080" + path
        headers = headers or {}
        if self.cookie:
            headers['Cookie'] = self.cookie
        
        try:
            req = urllib2.Request(url, data, headers)
            req.get_method = lambda: method
            return self.browser.do_request(req)
        except urllib2.HTTPError, e:
            raise OLError(e)

    def login(self, username, password):
        """Login to Open Library with given credentials.
        """
        headers = {'Content-Type': 'application/json'}  
        try:      
            data = simplejson.dumps(dict(username=username, password=password))
            response = self._request('/account/login', method='POST', data=data, headers=headers)
        except urllib2.HTTPError, e:
            response = e
        
        if 'Set-Cookie' in response.headers:
            cookies = response.headers['Set-Cookie'].split(',')
            self.cookie =  ';'.join([c.split(';')[0] for c in cookies])

    def get(self, key):
        data = self._request(key + '.json').read()
        return simplejson.loads(data)

    def save(self, key, data, comment=None):
        headers = {'Content-Type': 'application/json'}
        if comment:
            headers['Opt'] = '"http://openlibrary.org/dev/docs/api"; ns=42'
            headers['42-comment'] = comment
        data = simplejson.dumps(data)
        return self._request(key, method="PUT", data=data, headers=headers).read()
        
    def _call_write(self, name, query, comment, action):
        headers = {'Content-Type': 'application/json'}

        # use HTTP Extension Framework to add custom headers. see RFC 2774 for more details.
        if comment or action:
            headers['Opt'] = '"http://openlibrary.org/dev/docs/api"; ns=42'
        if comment:
            headers['42-comment'] = comment
        if action:
            headers['42-action'] = action

        response = self._request('/api/' + name, method="POST", data=simplejson.dumps(query), headers=headers)
        return simplejson.loads(response.read())

    def save_many(self, query, comment=None, action=None):
        return self._call_write('save_many', query, comment, action)
        
    def write(self, query, comment="", action=""):
        """Internal write API."""
        return self._call_write('write', query, comment, action)

    def new(self, query, comment=None, action=None):
        return self._call_write('new', query, comment, action)

def setup_module(module):
    b = ol.app.browser()
    b.open('/account/register')
    b.select_form(name='register')
    b['username'] = 'joe'
    b['displayname'] = 'Joe'
    b['password'] = 'secret'
    b['password2'] = 'secret'
    b['email'] = 'joe@example.com'
    b.submit()

    from infogami.plugins.api import code as api
    api.can_write = lambda: True

    b = ol.app.browser()
    b.check_errors = lambda: None
    module.olapi = OpenLibrary(b)

def test_write_with_embeddable_types():
    q = {
       'key': '/b/OL1M',
       'table_of_contents': {'connect': 'update_list', 'value': [
           {'type': '/type/toc_item', 'title': 'chapter 1'},
           {'type': '/type/toc_item', 'title': 'chapter 2'}
       ]},
    }
    olapi.login('joe', 'secret')
    olapi.write(q, comment="update toc")

    d = olapi.get('/b/OL1M')
    assert d['table_of_contents'] == [
        {"type": {"key": "/type/toc_item"}, "title": "chapter 1"},
        {"type": {"key": "/type/toc_item"}, "title": "chapter 2"},
    ]


def test_write_with_embeddable_types2():
    q = {
       'key': '/b/OL1M',
       'table_of_contents': {'connect': 'update_list', 'value': [
           {'title': 'chapter 1'},
           {'title': 'chapter 2'}
       ]},
    }
    olapi.login('joe', 'secret')
    olapi.write(q, comment="update toc")

    d = olapi.get('/b/OL1M')
    print d['table_of_contents']
    assert d['table_of_contents'] == [
        {"type": {"key": "/type/toc_item"}, "title": "chapter 1"},
        {"type": {"key": "/type/toc_item"}, "title": "chapter 2"},
    ]

def test_save():
    toc = [
        {"type": {"key": "/type/toc_item"}, "title": "chapter 1: x"},
        {"type": {"key": "/type/toc_item"}, "title": "chapter 2: x"},
    ]

    d = olapi.get('/b/OL1M')
    d['table_of_contents'] = toc
    print olapi.save("/b/OL1M", d)

    d = olapi.get('/b/OL1M')
    assert d['table_of_contents'] == toc

