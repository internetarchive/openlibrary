r"""Open Library API Client.

Sample Usage::

    ol = OpenLibrary("http://0.0.0.0:8080")
    ol.login('joe', 'secret')
    
    page = ol.get("/sandbox")
    print page["body"]

    page["body"] += "\n\nTest from API"
    ol.save("/sandbox", page, "test from api")
"""

__version__ = "0.1"
__author__ = "Anand Chitipothu <anandology@gmail.com>"


import os
import re
import datetime
from ConfigParser import ConfigParser
import urllib, urllib2
import simplejson
import web
import logging

logger = logging.getLogger("openlibrary.api")

class OLError(Exception):
    def __init__(self, http_error):
        self.code = http_error.code
        self.headers = http_error.headers
        msg = http_error.msg + ": " + http_error.read()
        Exception.__init__(self, msg)


class OpenLibrary:
    def __init__(self, base_url="https://openlibrary.org"):
        self.base_url = base_url.rstrip('/')
        self.cookie = None

    def _request(self, path, method='GET', data=None, headers=None):
        logger.info("%s %s", method, path)
        url = self.base_url + path
        headers = headers or {}
        if self.cookie:
            headers['Cookie'] = self.cookie
        
        try:
            req = urllib2.Request(url, data, headers)
            req.get_method = lambda: method
            return urllib2.urlopen(req)
        except urllib2.HTTPError, e:
            raise OLError(e)

    def autologin(self, section=None):
        """Login to Open Library with credentials taken from ~/.olrc file.

        The ~/.olrc file must be in ini format (format readable by
        ConfigParser module) and there should be a section with the
        server name. A sample configuration file may look like this::

            [openlibrary.org]
            username = joe
            password = secret

            [0.0.0.0:8080]
            username = joe
            password = joe123
            
        Optionally section name can be passed as argument to force using a different section name.

        If environment variable OPENLIBRARY_RCFILE is specified, it'll read that file instead of ~/.olrc.
        """
        config = ConfigParser()

        configfile = os.getenv('OPENLIBRARY_RCFILE', os.path.expanduser('~/.olrc'))
        logger.info("reading %s", configfile)
        config.read(configfile)
        
        section = section or self.base_url.replace('http://', '').replace("https://", "")

        if not config.has_section(section):
            raise Exception("No section found with name %s in ~/.olrc" % repr(section))

        username = config.get(section, 'username')
        password = config.get(section, 'password')
        return self.login(username, password)

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

    def get(self, key, v=None):
        data = self._request(key + '.json' + ('?v=%d' % v if v else '')).read()
        return unmarshal(simplejson.loads(data))
        
    def get_many(self, keys):
        """Get multiple documents in a single request as a dictionary.
        """
        if len(keys) > 500:
            # get in chunks of 500 to avoid crossing the URL length limit.
            d = {}
            for chunk in web.group(keys, 100):
                d.update(self._get_many(chunk))
            return d
        else:
            return self._get_many(keys)
        
    def _get_many(self, keys):
        response = self._request("/api/get_many?" + urllib.urlencode({"keys": simplejson.dumps(keys)}))
        return simplejson.loads(response.read())['result']

    def save(self, key, data, comment=None):
        headers = {'Content-Type': 'application/json'}
        data = marshal(data)
        if comment:
            headers['Opt'] = '"http://openlibrary.org/dev/docs/api"; ns=42'
            headers['42-comment'] = comment
        data = simplejson.dumps(data)
        return self._request(key, method="PUT", data=data, headers=headers).read()
        
    def _call_write(self, name, query, comment, action):
        headers = {'Content-Type': 'application/json'}
        query = marshal(query)

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

    def query(self, q=None, **kw):
        """Query Open Library.

        Open Library always limits the result to 1000 items due to
        performance issues. Pass limit=False to fetch all matching
        results by making multiple requests to the server. Please note
        the an iterator is returned insted of list when limit=False is
        passed.::

            >>> ol.query({'type': '/type/type', 'limit': 2}) #doctest: +SKIP
            [{'key': '/type/property'}, {'key': '/type/type'}]

            >>> ol.query(type='/type/type', limit=2) #doctest: +SKIP
            [{'key': '/type/property'}, {'key': '/type/type'}]
        """
        q = dict(q or {})
        q.update(kw)
        q = marshal(q)
        def unlimited_query(q):
            q['limit'] = 1000
            q.setdefault('offset', 0)
            q.setdefault('sort', 'key')

            while True:
                result = self.query(q)
                for r in result:
                    yield r
                if len(result) < 1000:
                    break
                q['offset'] += len(result)

        if 'limit' in q and q['limit'] == False:
            return unlimited_query(q)
        else:
            q = simplejson.dumps(q)
            response = self._request("/query.json?" + urllib.urlencode(dict(query=q)))
            return unmarshal(simplejson.loads(response.read()))


def marshal(data):
    """Serializes the specified data in the format required by OL.::

        >>> marshal(datetime.datetime(2009, 1, 2, 3, 4, 5, 6789))
        {'type': '/type/datetime', 'value': '2009-01-02T03:04:05.006789'}
    """
    if isinstance(data, list):
        return [marshal(d) for d in data]
    elif isinstance(data, dict):
        return dict((k, marshal(v)) for k, v in data.iteritems())
    elif isinstance(data, datetime.datetime):
        return {"type": "/type/datetime", "value": data.isoformat()}
    elif isinstance(data, Text):
        return {"type": "/type/text", "value": unicode(data)}
    elif isinstance(data, Reference):
        return {"key": unicode(data)}
    else:
        return data


def unmarshal(d):
    u"""Converts OL serialized objects to python.::

        >>> unmarshal({"type": "/type/text", "value": "hello, world"})
        <text: u'hello, world'>
        >>> unmarshal({"type": "/type/datetime", "value": "2009-01-02T03:04:05.006789"})
        datetime.datetime(2009, 1, 2, 3, 4, 5, 6789)
    """
    if isinstance(d, list):
        return [unmarshal(v) for v in d]
    elif isinstance(d, dict):
        if 'key' in d and len(d) == 1:
            return Reference(d['key'])
        elif 'value' in d and 'type' in d:
            if d['type'] == '/type/text':
                return Text(d['value'])
            elif d['type'] == '/type/datetime':
                return parse_datetime(d['value'])
            else:
                return d['value']
        else:
            return dict([(k, unmarshal(v)) for k, v in d.iteritems()])
    else:
        return d


def parse_datetime(value):
    """Parses ISO datetime formatted string.::

        >>> parse_datetime("2009-01-02T03:04:05.006789")
        datetime.datetime(2009, 1, 2, 3, 4, 5, 6789)
    """
    if isinstance(value, datetime.datetime):
        return value
    else:
        tokens = re.split('-|T|:|\.| ', value)
        return datetime.datetime(*map(int, tokens))


class Text(unicode):
    def __repr__(self):
        return "<text: %s>" % unicode.__repr__(self)


class Reference(unicode):
    def __repr__(self):
        return "<ref: %s>" % unicode.__repr__(self)
