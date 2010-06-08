"""Library to process edition, work and author records and emit (key, property, value) triples that can be combined later for solr indexing.
"""
import os
import simplejson
from dump import read_tsv, log

# PASS-1
# author: key, name, alternate_names, birth_date, death_date, works
# work: everything, except author details
# subjects: name, key, works
#
# pass-2: 
# compute work.edition_count, subject.count
#
#
# PASS-2
# go over each author and emit name, alternate names.
# go over each work and emit (author, "work_count", work)
# go over 

def subdict(d, properties):
    return dict((k, v) for k, v in d.iteritems() if k in set(properties))

def process_edition(doc):    
    properties = [
        'key',
        'isbn_10', 'isbn_13', 'lccn', 'oclc',
        'dewey_decimal_class', 'lc_classifications', 
        'publishers', 'publish_places', 'publish_date',
        'title', 'subtitle', 'languages', 'covers',
        'number_of_pages', 'pagination',
        'contributions'
    ]
    json = simplejson.dumps(subdict(doc, properties))
    return [(w['key'], 'edition', json) for w in doc.get('works', [])]

def fix_subjects(doc):
    """In some records, the subjects are references/text instead of string. This function fixes that."""
    def fix(s):
        if isinstance(s, dict):
            if 'value' in s:
                s = s['value']
            elif 'key' in s:
                s = s['key'].split("/")[-1].replace("_", " ")
        return s

    for name in ['subjects', 'subject_places', 'subject_people', 'subject_times']:
        if name in doc:
            doc[name] = [fix(s) for s in doc[name]]
    return doc
    
def get_subjects(doc):
    for s in doc.get('subjects', []):
        yield s, '/subjects/' + s.lower().replace(' ', '_')

    for s in doc.get('subject_places', []):
        yield s, '/subjects/place:' + s.lower().replace(' ', '_')

    for s in doc.get('subject_people', []):
        yield s, '/subjects/person:' + s.lower().replace(' ', '_')

    for s in doc.get('subject_times', []):
        yield s, '/subjects/time:' + s.lower().replace(' ', '_')    

def process_work(doc, author_db):
    doc = fix_subjects(doc)
    
    properties = [
        "title", "subtitle", "translated_titles", "other_titles",
        "authors", 
        "subjects", "subject_places", "subject_people", "subject_times", "genres",
    ]
    yield doc['key'], "json", simplejson.dumps(subdict(doc, properties))
    
    authors = [a['author']['key'] for a in doc.get('authors', []) if 'author' in a and 'key' in a['author']]
    for akey in set(authors):
        olid = akey.split("/")[-1]
        try:
            yield doc['key'], 'author', author_db[olid]
            yield akey, 'work', doc['key']
        except KeyError:
            pass
    for name, key in get_subjects(doc):
        yield key, "name", name
        yield key, "work", doc['key']
        for a in authors:
            yield a, "subject", key
        
def process_author(doc):
    key = doc['key']
    properties = ["name", "personal_name", "alternate_names", "birth_date", "death_date", "date"]
    return [(key, 'json', simplejson.dumps(subdict(doc, properties)))]

class Writer:
    def __init__(self):
        self.files = {}
        
    def get_filename(self, key):
        if key.startswith("/authors/"):
            return "authors.txt"
        elif key.startswith("/works/"):
            return "works_%02x" % (hash(key) % 256)
        elif key.startswith("/subjects/place:"):
            return "places.txt"
        elif key.startswith("/subjects/person:"):
            return "people.txt"
        elif key.startswith("/subjects/time:"):
            return "times.txt"
        elif key.startswith("/subjects/"):
            return "subjects.txt"
        else:
            return "unexpected.txt"
            
    def get_file(self, key):
        filename = self.get_filename(key)
        if filename not in self.files:
            self.files[filename] = open('solrdump/' + filename, 'w', 5*1024*1024)
        return self.files[filename]
        
    def write(self, tuples):
        tjoin = lambda *cols: "\t".join([web.safestr(c) for c in cols]) + "\n"
        for key, property, value in tuples:
            self.get_file(key).write(tjoin(key, property, value))
            
    def close(self):
        for f in self.files.values():
            f.close()
        self.files.clear()
        
    def flush(self):
        for f in self.files.values():
            f.flush()
            
def process_author_dump(writer, authors_dump):
    import bsddb 
    db = bsddb.btopen('solrdump/authors.db', 'w', cachesize=1024*1024*1024)
    
    properties = ['name', 'alternate_names', 'personal_name']
    for type, key, revision, timestamp, json in read_tsv(authors_dump):
        author = simplejson.loads(json)
        
        olid = key.split("/")[-1]        
        db[olid] = simplejson.dumps(subdict(author, properties))
        
        writer.write(process_author(author))
    return db
    
def process_work_dump(writer, works_dump, author_db):
    for type, key, revision, timestamp, json in read_tsv(works_dump):
        doc = simplejson.loads(json)
        writer.write(process_work(doc, author_db))
        
def process_edition_dump(writer, editions_dump):
    for type, key, revision, timestamp, json in read_tsv(editions_dump):
        doc = simplejson.loads(json)
        writer.write(process_edition(doc))
    
def generate_dump(editions_dump, works_dump, authors_dump, redirects_dump):
    writer = Writer()

    if not os.path.exists("solrdump"):
        os.makedirs("solrdump")
    
    author_db = process_author_dump(writer, authors_dump)
    process_work_dump(writer, works_dump, author_db)
    author_db.close()
    author_db = None
    
    process_edition_dump(writer, editions_dump)
    
    writer.close()
    log("done")
