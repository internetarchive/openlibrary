#! /usr/bin/env
"""Script to compare subject info in solr and couchdb.
"""
import sys
import simplejson
import web
import urllib2
import time

couchdb_url = "http://ia331510:5984/works/_design/seeds/_view/seeds"

def wget(url):
    print >> sys.stderr, time.asctime(), "wget", url
    return urllib2.urlopen(url).read()

def jsonget(url):
    return simplejson.loads(wget(url))

def get_couchdb_works(subject):
    url = couchdb_url + "?key=" + simplejson.dumps(subject)
    rows = jsonget(url)['rows']
    return [row['id'] for row in rows]
    
def get_subjects(work):
    def get(name, prefix):
        return [prefix + s.lower().replace(" ", "_") for s in work.get(name, []) if isinstance(s, basestring)]
        
    return get("subjects", "subject:") \
        + get("subject_places", "place:") \
        + get("subject_times", "time:") \
        + get("subject_people", "person:")
        
def get_solr_works(subject):
    subject = web.lstrips(subject, "subject:")
    url = "http://openlibrary.org/subjects/%s.json?limit=10000" % subject
    data = jsonget(url)
    return [w['key'] for w in data['works']]
    
def get_doc(key):
    doc = jsonget("http://openlibrary.org" + key + ".json")
    return doc
    
def compare_works(subject):
    solr_works = get_solr_works(subject)
    couch_works = get_couchdb_works(subject)
    
    works = dict((k, None) for k in solr_works + couch_works)
    for key in works:
        doc = get_doc(key)
        subjects = get_subjects(doc)
        works[key] = {"key": key, "subject": subject in subjects, "solr": key in solr_works, "couch": key in couch_works}
        
    for w in sorted(works.values(), key=lambda w: (w['solr'], w['couch'], w['subject'])):
        print w["key"], w['subject'], w['solr'], w['couch']

if __name__ == "__main__":
    compare_works(sys.argv[1])
