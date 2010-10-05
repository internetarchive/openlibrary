"""Script to test a list of archive ids are lendable or not.
"""
import simplejson
import yaml
import shelve
import urllib2

import xml.dom.minidom

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
            d['ia'] = _load_ia_data(ia)
            sh[ia_id] = d        

def _load_ia_data(ia):
    url = "http://www.archive.org/download/%(ia)s/%(ia)s_meta.xml" % locals()
    xml = urllib2.urlopen(url).read()
    
    dom = xml.dom.minidom.parseString(xml)
    
    def get_elements(name):
        return [e.childNodes[0].data for e in dom.getElementsByTagName(name)]

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

def load_amazon(shelve_file):
    sh = shelve.open(shelve_file)
    for i, k in enumerate(sh):
        d = sh[k]
        if 'amazon' not in d and d.get("ol", {}).get('isbn'):
            print i, "loading amazon data for ", k, d['ol']['isbn']
            isbns = d['ol']['isbn']
            data = dict((isbn, _load_amazon_data(isbn)) for isbn in isbns)
            data = dict((k, v) for k, v in d.items() if v is not None)
            d['amazon'] = data

def _load_amazon_data(isbn):
    url = "http://www.amazon.com/gp/product/%s" % isbn
    
    try:
        return urllib2.urlopen(url).geturl()
    except urllib2.HTTPError:
        return None
            
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
    print cmd, args
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
