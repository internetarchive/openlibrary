"""Script to find out-of-print books from a list of archive identifiers.

Availability of a book in print is found by checking OL and amazon.com for
latest edition and checking the published date.

This scripts uses [pyaws][1] library for querying amazon.com.

[1]: http://github.com/IanLewis/pyaws
"""
import simplejson
import yaml
import shelve
import urllib2
import re

from xml.dom import minidom
from ConfigParser import ConfigParser

from pyaws import ecs

def load_settings(settings_file):
    return yaml.safe_load(open(settings_file).read())

def jsonget(url):
    json = urllib2.urlopen(url).read()
    return simplejson.loads(json)

def load_ol_data(settings, ia_id):
    url = settings["works_solr"] + "/select?wt=json&q=ia:%s" % ia_id
    response = jsonget(url)
    docs = response['response']['docs']
    if docs:
        return docs[0]
    
def load_ol(settings_file, shelve_file, ia_ids_file):
    settings = load_settings(settings_file)
    sh = shelve.open(shelve_file)

    for ia_id in open(ia_ids_file):
        ia_id = ia_id.strip()

        d = sh.get(ia_id, {})
        
        if not d.get("ol"):
            print "loading ol data for", ia_id, d
            d['ol'] = load_ol_data(settings, ia_id)
            sh[ia_id] = d
            
def load_ia(shelve_file, ia_ids_file):
    sh = shelve.open(shelve_file)

    for i, ia_id in enumerate(open(ia_ids_file)):
        ia_id = ia_id.strip()
        d = sh.get(ia_id, {})
        if not d.get("ia"):
            print i, "loading ia data for", ia_id
    
            try:
                d['ia'] = _load_ia_data(ia_id)
                sh[ia_id] = d        
            except Exception:
                print "ERROR: failed to load ia data for", ia_id
                import traceback
                traceback.print_exc()
            
def _load_ia_data(ia):
    url = "http://www.archive.org/download/%(ia)s/%(ia)s_meta.xml" % locals()
    xml = urllib2.urlopen(url).read()
    
    dom = minidom.parseString(xml)
    
    def get_elements(name):
        return [e.childNodes[0].data for e in dom.getElementsByTagName(name) if e.childNodes]

    def get_element(name):
        try:
            return get_elements(name)[0]
        except IndexError:
            return None
        
    return {
        "title": get_element("title"),
        "authors": get_elements("creator"),
        "addeddate": get_element("addeddate"),
        "collections": get_elements("collections"),
        "publisher": get_element("publisher"),
        "date": get_element("date"),
        "mediatype": get_element("mediatype"),
    }            
    
def _setup_amazon_keys():
    config = ConfigParser()
    files = config.read([".amazonrc", "~/.amazonrc"])
    if not files:
        print >> sys.stderr, "ERROR: Unable to find .amazonrc with access keys."
    
    access_key = config.get("default", "access_key")
    secret = config.get("default", "secret")

    ecs.setLicenseKey(access_key)
    ecs.setSecretAccessKey(secret)
    
def load_amazon(shelve_file):
    _setup_amazon_keys()

    sh = shelve.open(shelve_file)
    for i, k in enumerate(sh):
        d = sh[k]
        if 'amazon' not in d and 'ia' in d:
            print i, "querying amazon for", k
            doc = d['ia']

            title = doc.get('title')
            authors = doc.get('authors')
            author = authors and authors[0] or ""
            
            d['amazon'] = _query_amazon(title, author)
            sh[k] = d

def _query_amazon(title, author):
    # strips dates from author names
    author = re.sub('[0-9-]+', ' ', author).strip()
    
    try:
        res = ecs.ItemSearch(None, SearchIndex="Books", Title=title, Author=author, ResponseGroup="ItemAttributes")
    except KeyError, e:
        # Ignore nomathes error
        if 'ECommerceService.NoExactMatches' in str(e):
            return []
        else:
            raise
            
    def process(x):
        x = x.__dict__
        
        # remove unwanted data
        x.pop("ItemLinks", None)
        x.pop("DetailPageURL", None)
        
        return x
        
    return [process(x) for x in take(50, res)]
    
def take(n, seq):
    """Takes first n elements from the seq."""
    seq = iter(seq)

    for i in range(n):
        yield seq.next()

def print_all(shelve_file):
    sh = shelve.open(shelve_file)
    for k in sh:
        print k + "\t" + simplejson.dumps(sh[k])
        
def debug(shelve_file):
    sh = shelve.open(shelve_file)
    for k in sh:
        d = sh[k]
        if 'ol' in d:
            doc = d['ol']
            
            title = doc.get('title')
            author = doc.get('author_name')
            author = author and author[0] or ""
            
            cols = [k, repr(title), repr(author)]
            print "\t".join(cols)

def help():
    print __doc__

def main(cmd, *args):
    if cmd == "load_ol":
        load_ol(*args)
    elif cmd == "load_ia":
        load_ia(*args)
    elif cmd == "load_amazon":
        load_amazon(*args)
    elif cmd == "print":
        print_all(*args)
    elif cmd == "debug":
        debug(*args)
    else:
        help()
    
if __name__ == "__main__":
    import sys
    main(*sys.argv[1:])
