import os, httplib, sys
import simplejson as json
from collections import defaultdict
from lxml.etree import tostring, Element 

def index_publishers(data_dir):
    dir = data_dir + '/b/'
    publishers = defaultdict(int)
    for f in os.listdir(dir):
        d = json.load(open(dir + f))
        for p in d.get('publishers', None) or []:
            publishers[p] += 1
    return publishers.items()

def index_authors(data_dir):
    dir = data_dir + '/a/'
    authors = {}
    for f in os.listdir(dir):
        d = json.load(open(dir + f))
        authors[d['key']] = dict((k, d[k]) for k in ('name', 'alternate_names', 'birth_date', 'death_date', 'dates') if k in d)
    return authors.items()

def solr_post(h, solr_url, body):
    h.request('POST', solr_url, body, { 'Content-type': 'text/xml;charset=utf-8'})
    response = h.getresponse()
    response_body = response.read()
    print response.reason

def add_field(doc, name, value):
    field = Element("field", name=name)
    field.text = unicode(value)
    doc.append(field)

def load_indexes(data_dir, solr_port):
    add = {}
    add['publishers'] = Element('add')
    for k, v in index_publishers(data_dir):
        doc = Element("doc")
        add_field(doc, 'name', k)
        add_field(doc, 'count', v)
        add['publishers'].append(doc)

    add['authors'] = Element('add')
    for key, a in index_authors(data_dir):
        doc = Element("doc")
        add_field(doc, 'key', key)
        for k, v in a.items():
            if k == 'alternate_names':
                assert isinstance(v, list)
                for value in v:
                    add_field(doc, k, value)
            else:
                add_field(doc, k, v)
        add['authors'].append(doc)

    #for t in 'works', 'authors', 'publishers':
    #for t in 'authors', 'publishers':
    for t in 'publishers', 'authors':
        h1 = httplib.HTTPConnection('localhost:%d' % solr_port)
        h1.connect()
        add_xml = tostring(add[t], pretty_print=True).encode('utf-8')
        solr_url = 'http://localhost:%d/solr/%s/update' % (solr_port, t)
        print solr_url
        solr_post(h1, solr_url, '<del><query>*:*</query></del>')
        solr_post(h1, solr_url, '<commit />')
        h1.close()

        h2 = httplib.HTTPConnection('localhost:%d' % solr_port)
        h2.connect()
        solr_post(h2, solr_url, add_xml)
        solr_post(h2, solr_url, '<commit />')
        solr_post(h2, solr_url, '<optimize />')
        h2.close()

data_dir = sys.argv[1]
solr_port = int(sys.argv[2])
assert solr_port > 1024
load_indexes(data_dir, solr_port)
