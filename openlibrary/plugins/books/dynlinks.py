import urllib2
import urllib
import simplejson
import web
import os

debug = True

def api_things(key, value, details=False):
    query = {
        'type': '/type/edition',
        key: value,
        '*': None,
    }
    # all book info is anyway requred to check if that book has fulltext available or not.
    # Request for author names only when details are true.
    if details:
        query['authors'] = {'name': None}
    return web.ctx.site.things(query, details=True)

def get_thumbnail_url(key):
    olid = key.split('/')[-1]
    try:
        result = urllib2.urlopen('http://covers.openlibrary.org/b/query?limit=1&olid=' + olid).read()
        ids = simplejson.loads(result)
    except (urllib2.HTTPError, ValueError):
        ids = []
    if ids:
        return 'http://covers.openlibrary.org/b/id/%s-S.jpg' % ids[0]

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
        if len(value.replace('-', '')) == 13:
            key = 'isbn_13'
        else:
            key = 'isbn_10'

    if key == 'oclc':
        key = 'oclc_numbers'
        
    if key == 'olid':
        key = 'key'
        value = '/b/' + value.upper()

    return key, value
    
def process_result(bib_key, page, details):
    key = page['key']
    
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
        d['details'] = page
    return d
    
def find_olns(bib_keys, details):
    """Returns OLN for each of the bib_keys. Returns a dict with mapping from bib_key to OLN."""
    
    # find the key and value to query
    d = {}
    for bib_key in bib_keys:
        k, v = split_key(bib_key)
        if k is None:
            continue
        d[bib_key] = k, v
    
    # prepare queries
    queries = {}
    for k, v in d.values():
        queries.setdefault(k, []).append(v)

    # run queries and accumulate the result
    result = {}
    for k, q in queries.items():
        for thing in api_things(k, q, details):
            print >> web.debug, q, thing
            value = thing[k]
            if isinstance(value, list):
                for v in value:
                    result[k, v] = thing
            else:
                result[k, value] = thing
        
    # assign result to respective bib_key
    mapping = {}    
    for bib_key, (k, v) in d.items():
        if (k, v) in result:
            mapping[bib_key] = process_result(bib_key, result[k, v], details)
    return mapping

def get_multi(bib_keys, details=False):
    try:
        return find_olns(bib_keys, details)
    except:
        # this should never happen, but to protect from unexpected errors
        return {}
