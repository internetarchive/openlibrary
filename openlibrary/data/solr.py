"""Library to process edition, work and author records and emit (key, property, value) triples that can be combined later for solr indexing.
"""
import os, sys
import re
import web
import simplejson
import subprocess
import collections
import glob
import itertools

from dump import read_tsv, log

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

def process_work(doc, author_db, redirect_db):
    doc = fix_subjects(doc)
    
    properties = [
        "title", "subtitle", "translated_titles", "other_titles",
        "subjects", "subject_places", "subject_people", "subject_times", "genres",
    ]
    yield doc['key'], "json", simplejson.dumps(subdict(doc, properties))
    
    authors = [a['author']['key'] for a in doc.get('authors', []) if 'author' in a and 'key' in a['author']]
    for akey in set(authors):
        akey = find_redirect(redirect_db, akey) or akey
        olid = akey.split("/")[-1]
        
        try:
            yield doc['key'], 'author', author_db[olid]
            yield akey, 'work', doc['key']
        except KeyError:
            print >> sys.stderr, "notfound", akey
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
            return "authors_%02d.txt" % (hash(key) % 8)
        elif key.startswith("/works/"):
            return "works_%02d.txt" % (hash(key) % 64)
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
        
    def write(self, triples):
        tjoin = lambda *cols: "\t".join([web.safestr(c) for c in cols]) + "\n"
        for key, property, value in triples:
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
    
    properties = ['key', 'name', 'alternate_names', 'personal_name']
    for type, key, revision, timestamp, json in read_tsv(authors_dump):
        author = simplejson.loads(json)
        
        olid = key.split("/")[-1]        
        db[olid] = simplejson.dumps(subdict(author, properties))
        
        writer.write(process_author(author))
    return db

def process_redirect_dump(writer, redirects_dump):
    import bsddb 
    db = bsddb.btopen('solrdump/redirects.db', 'w', cachesize=1024*1024*1024)

    for type, key, revision, timestamp, json in read_tsv(redirects_dump):
        d = simplejson.loads(json)
        if not key.startswith("/authors/") and not key.startswith("/works/"):
            continue

        location = d.get('location')
        if location:
            # Old redirects still start with /a/ instead of /authors/.
            location = location.replace("/a/", "/authors/")
            db[key] = location
    
    for key in db:
        if key.startswith("/works/"):
            redirect = find_redirect(db, key)
            if redirect:
                writer.write([(redirect, "redirect", key)])
            
    return db
            
def find_redirect(redirect_db, key):
    """Finds the redirection of the given key if any.
    
    When there is a redirection for the given key, the redirection is returned.
    
        >>> db = {'/authors/OL1A': '/authors/OL2A'}
        >>> find_redirect(db, '/authors/OL1A')
        '/authors/OL2A'
        
    If there is no redirection, same key is returned.
        
        >>> find_redirect(db, '/authors/OL3A')
        '/authors/OL3A'
        
    Multiple levels of redirections are followed.

        >>> db = {'/authors/OL1A': '/authors/OL2A', '/authors/OL2A': '/authors/OL3A'}
        >>> find_redirect(db, '/authors/OL1A')
        '/authors/OL3A'

    In case of cyclic redirections, None is returned.

        >>> db = {'/authors/OL1A': '/authors/OL2A', '/authors/OL2A': '/authors/OL1A'}
        >>> find_redirect(db, '/authors/OL1A')
    """
    for i in range(5):
        redirect = redirect_db.get(key)
        if not redirect:
            return key
        else:
            key = redirect
            
    return None
    
def process_work_dump(writer, works_dump, author_db, redirect_db):
    for type, key, revision, timestamp, json in read_tsv(works_dump):
        doc = simplejson.loads(json)
        writer.write(process_work(doc, author_db, redirect_db))
        
def process_edition_dump(writer, editions_dump):
    for type, key, revision, timestamp, json in read_tsv(editions_dump):
        doc = simplejson.loads(json)
        writer.write(process_edition(doc))
    
def generate_dump(editions_dump, works_dump, authors_dump, redirects_dump):
    pharse1_process_dumps(editions_dump, works_dump, authors_dump, redirects_dump)
    phase2_process_files()
    
def pharse1_process_dumps(editions_dump, works_dump, authors_dump, redirects_dump):    
    writer = Writer()
    if not os.path.exists("solrdump"):
        os.makedirs("solrdump")

    redirect_db = process_redirect_dump(writer, redirects_dump)
    author_db = process_author_dump(writer, authors_dump)    
    process_work_dump(writer, works_dump, author_db, redirect_db)
    author_db.close()
    author_db = None
    
    process_edition_dump(writer, editions_dump)
    writer.close()
    writer = None
    log("done")
    
def phase2_process_files():
    f = open("solrdump/solrdump_works.txt", "w", 5*1024*1024)
    
    for path in glob.glob("solrdump/works_*"):
        f.writelines("%s\t%s\n" % (key, simplejson.dumps(process_solr_work_record(key, d))) 
            for key, d in process_triples(path))
        
def process_work_triples(path):
    for key, work in process_triples(path):
        yield key, process_work_triples(key, work)

re_year = re.compile(r'(\d{4})$')
        
def process_solr_work_record(key, d):            
    editions = d.pop('edition', [])
    authors = d.pop('author', [])
    redirects = d.pop('redirect', [])    
    work = d.pop('json')[0]

    def basename(path):
        return path.split("/")[-1]

    def put(k, v):
        if v:
            r[k] = v
    
    def mput(k, v):
        if v is None:
            return
        elif isinstance(v, list):
            r[k].extend(v)
        else:
            r[k].append(v)
        
    r = collections.defaultdict(list)

    put("key", basename(key))
    put("title", work.get("title"))
    put("subtitle", work.get("subtitle"))
    
    r['edition_count'] = len(editions)
    
    for e in editions:
        mput("oclc", e.get("oclc_numbers"))
        mput("oclc", e.get("lccn"))
        mput("isbn", e.get("isbn_10"))
        mput("isbn", e.get("isbn_13"))
        
        mput("publisher", e.get("publishers"))
        mput("publish_place", e.get("publish_places"))
        
        mput("ia", e.get("ocaid"))
        mput("language", e.get("languages"))
        mput("number_of_pages", e.get("number_of_pages"))
        
        mput("contributor", e.get("contributions"))
        mput("publish_date", e.get("publish_date"))
        
    for a in authors:
        mput("author_name", a.get("name", ""))
        mput("author_key", basename(a['key']))
        mput("author_alternative_name", a.get("alternate_names"))
        
    r['ia_count'] = len(r['ia'])
    r['has_fulltext'] = bool(r['ia'])
    
    r['publish_year'] = [m.group(1) for m in [re_year.match(date) for date in r['publish_date']] if m]
    if r['publish_year']:
        r['first_publish_year'] = min(r['publish_year'])
        
    ## special processing
    # strip - from ISBNS
    r['isbn'] = [isbn.replace("-", "") for isbn in r['isbn']]
    
    # {"key": "/languages/eng"} -> "eng"
    r['language'] = [basename(lang['key']) for lang in r['language']]
    
    # push google scans to the end
    r['ia'] = [ia for ia in r['ia'] if not ia.startswith("goog")] + [ia for ia in r['ia'] if ia.startwith("goog")]

    r['author_facet'] =  [' '.join(v) for v in zip(r['author_keys'], r['author_names'])]
    return r

def process_triples(path):
    """Takes a file with triples, sort it using first column and groups it by first column.
    """
    print "processing triples from", path
    cmd = ["sort", path]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    for key, chunk in itertools.groupby(read_tsv(p.stdout), lambda t: t[0]):
        d = collections.defaultdict(list)
        for k, name, value in chunk:
            if name in ['json', 'edition', 'author']:
                value = simplejson.loads(value)
            d[name].append(value)
        yield key, d
    
if __name__ == "__main__":
    import doctest
    doctest.testmod()
    