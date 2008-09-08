import urllib2
import urllib
import simplejson
import web
import os

debug = True

def get_site():
    return web.ctx.home

def api_things(key, value):
    query = {
        'type': '/type/edition',
        key: value
    }
    try:
        d = urllib.urlopen(get_site() + '/api/things?' + urllib.urlencode(dict(query=simplejson.dumps(query))))
        data = simplejson.loads(d.read())
        if data['status'] == 'ok':
            return data['result']
    except:
        import traceback
        traceback.print_exc()
        return []

def api_get(key):
    try:
        d = urllib.urlopen(get_site() + '/api/get?' + urllib.urlencode(dict(key=key)))
        data = simplejson.loads(d.read())
        if data['status'] == 'ok':
            return data['result']
    except:
        return {}

def cond(p, c, a=None):
    if p: return c
    else: return a

def get_thumbnail(page):
    try:
        coverimage = page.get('coverimage') and page.get('coverimage') != "/static/images/book.trans.gif"
        if coverimage:
            return coverimage

        if page.get('isbn_10') and len(page['isbn_10'][0]) == 10:
            isbn = page['isbn_10'][0]
            path = 'static/bookcovers/thumb/%s/%s/%s.jpg' % (isbn[0], isbn[1], isbn)
            if os.path.exists(path):
                return '/' + path
    except:
        import traceback
        traceback.print_exc()

    return '/static/logos/logo-en.jpg'

def make_data(bib_key, olid):
    page = api_get(olid)
    if 'ocaid' in page:
        preview = 'full'
        preview_url = 'http://openlibrary.org/details/' + page['ocaid']
    else:
        preview = 'noview'
        preview_url = 'http://openlibrary.org' + olid
    thumbnail_url = 'http://openlibrary.org' + get_thumbnail(page)
    
    return {
        'bib_key': bib_key,
        'info_url': 'http://openlibrary.org' + olid,
        'preview': preview,
        'preview_url': preview_url,
        'thumbnail_url': thumbnail_url,
    }

def split_key(bib_key):
    """
        >>> split_key('1234567890')
        ('isbn_10', '1234567890')
        >>> split_key('ISBN:1234567890')
        ('isbn_10', '1234567890')
        >>> split_key('ISBN1234567890')
        ('isbn_10', '1234567890')
        >>> split_key('ISBN1234567890123')
        ('isbn_13', '1234567890123')
        >>> split_key('LCCNsa 64009056')
        ('lccn', 'sa 64009056')
        >>> split_key('badkey')
        (None, None)
    """
    bib_key = bib_key.lower().strip()
    if not bib_key:
        return None, None

    valid_keys = ['isbn', 'lccn', 'oclc']
    key, value = None, None

    # split with : when possible
    if ':' in bib_key:
        key, value = bib_key.split(':', 1)
        key = key.lower()
    else:
        # try prefix match
        for k in valid_keys:
            if bib_key.startswith(k):
                key = k
                value = bib_key[len(k):]
                continue

    # treat plain number as ISBN
    if key is None and bib_key[0].isdigit():
        key = 'isbn'
        value = bib_key
        
    # decide isbn_10 or isbn_13 based on length.
    if key == 'isbn':
        if len(value) == 13:
            key = 'isbn_13'
        else:
            key = 'isbn_10'

    if key == 'oclc':
        key = 'oclc_numbers'

    return key, value
        
def get(bibkey):
    key, value = split_key(bibkey)
    things = key and api_things(key, value)
    return things and {bibkey: make_data(bibkey, things[0])}

def get_multi(bib_keys):
    try:
        result = {}
        for bib_key in bib_keys:
            d = get(bib_key)
            d and result.update(d)
        return result
    except:
        # this should never happen, but to protect from unexpected errors
        return {}
