"""Code for handling /data/*.txt.gz URLs.
"""
import web
from infogami.utils import delegate
from infogami.utils.view import public

import simplejson
import urllib2

def wget(url):
    return urllib2.urlopen(url).read()

def get_ol_dumps():
    """Get list of all archive.org items in the in the ol_exports collection uploaded of archive.org staff."""
    url = 'http://www.archive.org/advancedsearch.php?q=(ol_dump+OR+ol_cdump)+AND+collection:ol_exports+AND+uploader:(%40archive.org)&fl[]=identifier&output=json&rows=100'
    
    d = simplejson.loads(wget(url))
    return sorted(doc['identifier'] for doc in d['response']['docs'])
    
# cache the result for half an hour
get_ol_dumps = web.memoize(get_ol_dumps, 30*60, background=True)
#public(get_ol_dumps)

def download_url(item, filename):
    return "http://www.archive.org/download/%s/%s" % (item, filename)

class ol_dump_latest(delegate.page):
    path = "/data/ol_dump(|_authors|_editions|_works|_deworks)_latest.txt.gz"
    def GET(self, prefix):
        items = [item for item in get_ol_dumps() if item.startswith("ol_dump")]
        if not items:
            raise web.notfound()
            
        item = items[-1]
        filename = item.replace("dump", "dump" + prefix) + ".txt.gz"
        raise web.found(download_url(item, filename))
        
class ol_cdump_latest(delegate.page):
    path = "/data/ol_cdump_latest.txt.gz"
    
    def GET(self):
        items = [item for item in get_ol_dumps() if item.startswith("ol_cdump")]
        if not items:
            raise web.notfound()
            
        item = items[-1]
        raise web.found(download_url(item, item + ".txt.gz"))
        
class ol_dumps(delegate.page):
    path = "/data/ol_dump(|_authors|_editions|_works)_(\d\d\d\d-\d\d-\d\d).txt.gz"
    
    def GET(self, prefix, date):
        item = "ol_dump_" + date
        if item not in get_ol_dumps():
            raise web.notfound()
        else:
            filename = "ol_dump" + prefix + "_" + date + ".txt.gz"
            raise web.found(download_url(item, filename))
            
class ol_cdumps(delegate.page):
    path = "/data/ol_cdump_(\d\d\d\d-\d\d-\d\d).txt.gz"
    def GET(self, date):
        item = "ol_cdump_" + date
        if item not in get_ol_dumps():
            raise web.notfound()
        else:
            raise web.found(download_url(item, item + ".txt.gz"))

def setup():
    pass