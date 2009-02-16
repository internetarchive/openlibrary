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
    return web.ctx.site.things(query)

def api_get(key):
    try:
        return web.ctx.site._get(key)
    except:
        return {}

def cond(p, c, a=None):
    if p: return c
    else: return a
    
def get_thumbnail_url(key):
    olid = key.split('/')[-1]
    try:
        result = urllib2.urlopen('http://covers.openlibrary.org/b/query?limit=1&olid=' + olid).read()
        ids = simplejson.loads(result)
    except (urllib2.HTTPError, ValueError):
        ids = []
    if ids:
        return 'http://covers.openlibrary.org/b/olid/%s-S.jpg' % olid
        
def get_details(page):
    def get_author(key):
        return {'key': key, 'name': api_get(key).get('name', '')}
    
    key = page['key']
    
    title_prefix = page.get('title_prefix') or ''
    title = page.get('title') or ''
    if title_prefix:
        title = title_prefix + ' ' + title
    
    publishers = page.get('publishers') or []
    
    authors = page.get('authors') or []
    authors = [get_author(a) for a in authors]
    
    by_statement = page.get('by_statement') or ''

    contributors = page.get('contributors') or ''
    publish_places = page.get('publish_places') or []
    publish_country = page.get('publish_country') or ''
    isbn_10 = page.get('isbn_10', [])
    isbn_13 = page.get('isbn_13', [])
    lccn = page.get('lccn', [])
    oclc_numbers = page.get('oclc_numbers', [])
    
    return dict(key=key, 
        title=title, 
        authors=authors, 
        contributors=contributors,
        by_statement=by_statement,
        publishers=publishers, 
        publish_places=publish_places,
        publish_country=publish_country,
        isbn_10=isbn_10,
        isbn_13=isbn_13,
        lccn=lccn,
        oclc_numbers=oclc_numbers,
    )

def make_data(bib_key, key, details=False):
    page = api_get(key)
    if 'ocaid' in page:
        preview = 'full'
        preview_url = 'http://openlibrary.org/details/' + page['ocaid']
    else:
        preview = 'noview'
        preview_url = 'http://openlibrary.org' + key
        
    thumbnail_url = get_thumbnail_url(key)
    
    d = {
        'bib_key': bib_key,
        'info_url': 'http://openlibrary.org' + key,
        'preview': preview,
        'preview_url': preview_url,
    }
    if thumbnail_url:
        d['thumbnail_url'] = thumbnail_url
        
    if details:
        d['details'] = get_details(page)
        
    return d

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

    valid_keys = ['isbn', 'lccn', 'oclc', 'ocaid', 'olid']
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
        
    # treat OLxxxM as OLID
    if key is None and bib_key.startswith('ol') and bib_key.endswith('m'):
        key = 'olid'
        value = bib_key
    
    # decide isbn_10 or isbn_13 based on length.
    if key == 'isbn':
        if len(value) == 13:
            key = 'isbn_13'
        else:
            key = 'isbn_10'

    if key == 'oclc':
        key = 'oclc_numbers'
        
    if key == 'olid':
        key = 'key'
        value = '/b/' + value.upper()

    return key, value
        
def get(bibkey, details=False):
    key, value = split_key(bibkey)
    things = key and api_things(key, value)
    return things and {bibkey: make_data(bibkey, things[0], details=details)}

def get_multi(bib_keys, details=False):
    try:
        result = {}
        for bib_key in bib_keys:
            d = get(bib_key, details=details)
            d and result.update(d)
        return result
    except:
        # this should never happen, but to protect from unexpected errors
        return {}
