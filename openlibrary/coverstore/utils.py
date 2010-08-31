"""Utilities for coverstore"""

import urllib, urllib2
import socket
import os
import mimetypes
import Image
import simplejson
import web

import random
import string

import config
import oldb

class AppURLopener(urllib.FancyURLopener):
    version = "Mozilla/5.0 (Compatible; coverstore downloader http://covers.openlibrary.org)"

socket.setdefaulttimeout(10.0)
urllib._urlopener = AppURLopener()

def safeint(value, default=None):
    """
        >>> safeint('1')
        1
        >>> safeint('x')
        >>> safeint('x', 0)
        0
    """
    try:
        return int(value)
    except:
        return default

def get_ol_url():
    return web.rstrips(config.ol_url, "/")
    
def ol_things(key, value):
    if oldb.is_supported():
        return oldb.query(key, value)
    else:
        query = {
            'type': '/type/edition',
            key: value, 
            'sort': 'last_modified',
            'limit': 10
        }
        try:
            d = dict(query=simplejson.dumps(query))
            result = download(get_ol_url() + '/api/things?' + urllib.urlencode(d))
            result = simplejson.loads(result)
            return result['result']
        except IOError:
            import traceback
            traceback.print_exc()
            return []
        
def ol_get(olkey):
    if oldb.is_supported():
        return oldb.get(olkey)
    else:
        try:
            result = download(get_ol_url() + olkey + ".json")
            return simplejson.loads(result)
        except IOError:
            return None

USER_AGENT = "Mozilla/5.0 (Compatible; coverstore downloader http://covers.openlibrary.org)"
def download(url):
    req = urllib2.Request(url, headers={'User-Agent': USER_AGENT})
    r = urllib2.urlopen(req)
    return r.read()

def urldecode(url):
    """
        >>> urldecode('http://google.com/search?q=bar&x=y')
        ('http://google.com/search', {'q': 'bar', 'x': 'y'})
        >>> urldecode('http://google.com/')
        ('http://google.com/', {})
    """
    base, query = urllib.splitquery(url)
    query = query or ""
    items = [item.split('=', 1) for item in query.split('&') if '=' in item]
    d = dict((urllib.unquote(k), urllib.unquote_plus(v)) for (k, v) in items)
    return base, d

def changequery(url, **kw):
    """
        >>> changequery('http://google.com/search?q=foo', q='bar', x='y')
        'http://google.com/search?q=bar&x=y'
    """
    base, params = urldecode(url)
    params.update(kw)
    return base + '?' + urllib.urlencode(params)

def read_file(path, offset, size, chunk=50*1024):
    """Returns an iterator over file data at specified offset and size.    
    
        >>> len("".join(read_file('/dev/urandom', 100, 10000)))
        10000
    """
    f = open(path)
    f.seek(offset)
    while size:
        data = f.read(min(chunk, size))
        size -= len(data)
        if data:
            yield data
        else:
            f.close()
            raise IOError("file truncated")
    f.close()
    
def rm_f(filename):
    try:
        os.remove(filename)
    except OSError:
        pass

chars = string.letters + string.digits
def random_string(n):
    return "".join([random.choice(chars) for i in range(n)])
    
def urlencode(data):
    """
    urlencodes the given data dictionary. If any of the value is a file object, data is multipart encoded.
    
    @@@ should go into web.browser
    """
    multipart = False
    for v in data.values():
        if isinstance(v, file):
            multipart = True
            break
            
    if not multipart:
        return 'application/x-www-form-urlencoded', urllib.urlencode(data)
    else:
        # adopted from http://code.activestate.com/recipes/146306/
        def get_content_type(filename):
            return mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        
        def encode(key, value, out):
            if isinstance(value, file):
                out.append('--' + BOUNDARY)
                out.append('Content-Disposition: form-data; name="%s"; filename="%s"' % (key, value.name))
                out.append('Content-Type: %s' % get_content_type(value.name))
                out.append('')
                out.append(value.read())
            elif isinstance(value, list):
                for v in value:
                    encode(key, v)
            else:
                out.append('--' + BOUNDARY)
                out.append('Content-Disposition: form-data; name="%s"' % key)
                out.append('')
                out.append(value)

        BOUNDARY = "----------ThIs_Is_tHe_bouNdaRY_$"
        CRLF = '\r\n'
        out = []
        for k, v in data.items():
            encode(k, v, out)
        body = CRLF.join(out)
        content_type = 'multipart/form-data; boundary=%s' % BOUNDARY
        return content_type, body

if __name__ == "__main__":
    import doctest
    doctest.testmod()
