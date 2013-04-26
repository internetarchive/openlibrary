"""Script to generate denormalizied works dump.

USAGE:

    python scripts/2011/09/generate_deworks.py ol_dump_latest.txt.gz | gzip -c > ol_dump_deworks.txt.gz


Output Format:

Each row contains a JSON document with the following fields:

* work - The work documents
* editions - List of editions that belong to this work
* authors - All the authors of this work
* ia - IA metadata for all the ia items referenced in the editions as a list
* duplicates - dictionary of duplicates (key -> it's duplicates) of work and edition docs mentioned above

CHANGELOG:

2013-04-26: Changed the format of denormalized documents and included duplicates/redirects.
2012-10-31: include IA metadata in the response
2012-03-15: print the output to stdout so that it can be piped though gzip
2011-10-04: first version

"""
import time
import sys
import gzip
import simplejson
import itertools
import os
import logging
#import bsddb
import zlib
import subprocess
import web
from collections import defaultdict
import re
import shutil

from openlibrary.data import mapreduce
from openlibrary.utils import compress


try:
    import bsddb
except ImportError:
    #import bsddb3 as bsddb
    pass

logger = logging.getLogger(None)

class DenormalizeWorksTask(mapreduce.Task):
    """Map reduce task to generate denormalized works dump from OL dump.
    """
    def __init__(self, ia_metadata):
        mapreduce.Task.__init__(self)
        self.ia = ia_metadata
        self.authors = AuthorsDict()
        self.duplicates = defaultdict(list)

    def get_ia_metadata(self, identifier):
        row = self.ia.get(identifier)
        if row:
            boxid, collection_str = row.split("\t")
            collections = collection_str.split(";")
            return {"boxid": [boxid], "collections": collections}
        else:
            # the requested identifier is not found.
            # returning a fake metadata
            return {"collections":[]}

    def close(self):
        """Removes all the temp files created for running map-reduce.
        """
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def map(self, key, value):
        """Takes key and json as inputs and emits (work-key, work-json) or (work-key, edition-json)
        for work and edition records respectively.
        """
        doc = simplejson.loads(value)
        type_key = doc['type']['key']
        
        if type_key == '/type/edition':
            if doc.get('works'):
                yield doc['works'][0]['key'], value
            else:
                yield doc['key'], value
        elif type_key == '/type/work':
            yield doc['key'], value
        elif type_key == '/type/author':
            # Store all authors for later use
            self.authors[key] = doc
        elif type_key == '/type/redirect':
            self.duplicates[doc.get("location")].append(key)

    def process_edition(self, e):
        if "ocaid" in e:
            ia = self.get_ia_metadata(e["ocaid"])
            if ia is not None:
                e['_ia_meta'] = ia

    def reduce(self, key, values):
        docs = {}
        for json in values:
            doc = simplejson.loads(json)
            self.process_edition(doc)
            docs[doc['key']] = doc
            
        if key.startswith("/works/"):
            work = docs.pop(key, {})
        else:
            # work-less edition
            work = {}

        doc = {}
        doc['work'] = work
        doc['editions'] = docs.values()
        doc['authors'] = [self.get_author_data(a['author']) for a in work.get('authors', []) if 'author' in a]

        ia_ids = [e['ocaid'] for e in doc['editions'] if e.get('ocaid') and e['ocaid'] in self.ia]
        doc['ia'] = [self.get_ia_metadata(ia_id) for ia_id in ia_ids]

        keys = set()
        keys.add(work.get("key"))
        keys.update(e.get("key") for e in doc['editions'])
        if None in keys:
            keys.remove(None)

        duplicates = [(k, self.get_duplicates(k)) for k in keys]
        duplicates = [(k, dups) for k, dups in duplicates if dups]
        doc['duplicates'] = dict(duplicates)
        return key, simplejson.dumps(doc)

    def get_duplicates(self, key, result=None, level=0):
        if result is None:
            result = set()

        # Avoid infinite recursion in case of mutual redirects
        if level >= 10:
            return result

        for k in self.duplicates[key]:
            result.add(k) # add the duplicate and all it's duplicates
            self.get_duplicates(k, result, level+1)

        return result

    def get_author_data(self, author):
        def get(key):
            return self.authors.get(key, {"key": key})

        if 'key' in author:
            key = author['key']
            return get(key)
        elif 'author' in author and 'key' in author['author']:
            key = author['author']['key']
            return {"author": get(key)}
        else:
            return author

class AuthorsDict:
    """Dictionary for storing author records in memory very efficiently.
    """
    re_author = re.compile("/authors/OL(\d+)A")
    chunk_size = 100

    def __init__(self):
        self.d = defaultdict(lambda: [None] * self.chunk_size)
        self.z = compress.Compressor('{"name": "", "personal_name": ""}')

    def __len__(self):
        return len(d)

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def __getitem__(self, key):
        try:
            m = self.re_author.match(key)
        except TypeError:
            print repr(key)
            raise
        if m:
            index = int(m.group(1))
            index0 = index / self.chunk_size
            index1 = index % self.chunk_size
            try:
                value = self.d[index0][index1]
            except (KeyError, IndexError):
                raise KeyError(key)
            if value is None:
                raise KeyError(key)
        else:
            value = self.d[key]
        doc = self.decode(value)
        doc['key'] = key
        return doc

    def __setitem__(self, key, value):
        m = self.re_author.match(key)
        if m:
            index = int(m.group(1))
            index0 = index / self.chunk_size
            index1 = index % self.chunk_size
            self.d[index0][index1] = self.encode(value)
        else:
            self.d[key] = self.encode(value)

    def encode(self, doc):
        for k in ['type', 'key', 'latest_revision', 'revision', 'last_modified', 'created']:
            doc.pop(k, None)
        return self.z.compress(simplejson.dumps(doc))

    def decode(self, text):
        doc = simplejson.loads(self.z.decompress(text))
        doc['type'] = {'key': '/type/author'}
        return doc
        
def xopen(filename, mode='r'):
    if filename.endswith(".gz"):
        return gzip.open(filename, mode)
    elif filename == "-":
        if mode == "r":
            return sys.stdin
        else:
            return sys.stdout
    else:
        return open(filename, mode)

def read_ia_metadata(filename):
    logger.info("BEGIN reading " + filename)
    t0 = time.time()
    N = 500000
    d = {}
    for i, line in enumerate(xopen(filename)):
        if i % N == 0:
            logger.info("reading line %d" % i)
        id, rest = line.strip("\n").split("\t", 1)
        d[id] = rest
    logger.info("END reading " + filename)
    return d
        
def read_dump(filename):
    t0 = time.time()
    N = 50000
    for i, line in enumerate(xopen(filename)):
        if i % N == 0:
            t1 = time.time()
            dt = t1-t0
            rate = dt and (N/dt)
            t0 = t1
            logger.info("reading %d (%d docs/sec)", i, rate)
        _type, key, _revision, _last_modified, jsondata = line.strip().split("\t")
        yield key, jsondata
    
def mkdir_p(path):
    if not os.path.exists(path):
        os.makedirs(path)
        
def main(dumpfile, ia_dumpfile):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    ia_metadata = read_ia_metadata(ia_dumpfile)
    records = read_dump(dumpfile)
    task = DenormalizeWorksTask(ia_metadata)

    for key, json in task.process(records):
        print key + "\t" + json

    task.close()
    
def make_author_db(author_dump_file):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    os.system("rm -rf authors.sqlite")
    db = web.database(dbn="sqlite", db="authors.sqlite")
    db.printing = False
    db.query("CREATE TABLE docs (key text, value blog)")
    db.query("PRAGMA cachesize=%d" % (1024*1024*100))
    db.query("PRAGMA synchronous=OFF")
    db.query("PRAGMA journal_mode=OFF")

    for chunk in web.group(read_dump(author_dump_file), 1000):
        t = db.transaction()
        for key, value in chunk:
            db.insert("docs", key=key, value=value)
        t.commit()

    logger.log("BEGIN create index")
    db.query("CREATE UNIQUE INDEX key_index ON docs(key)")
    logger.log("END create index")
    
def make_ia_db(editions_dump_file):
    #logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    #global logger
    #logger = logging.getLogger("openlibrary")
    logger.info("BEGIN make_ia_db %s", editions_dump_file)
    
    #db = bsddb.hashopen("ia.db", cachesize=1024*1024*500)
    
    #from openlibrary.core import ia
    
    f = open("ocaids.txt", "w")

    for key, json in read_dump(editions_dump_file):
        if "ocaid" in json:
            doc = simplejson.loads(json)
            ocaid = doc.get('ocaid')
            print >> f, ocaid
            """
            if ocaid:
                metaxml = ia.get_meta_xml(ocaid)
                db[ocaid] = simplejson.dumps(metaxml)
            """
    f.close()
    #db.close()

def test_AuthorsDict():
    d = AuthorsDict()
    
    docs = [
        {"key": "/authors/OL1A", "type": {"key": "/type/author"}, "name": "foo"},
        {"key": "/authors/OL2A", "type": {"key": "/type/author"}, "name": "bar"},
        {"key": "bad-key", "name": "bad doc", "type": {"key": "/type/author"}},
    ]

    for doc in docs:
        d[doc['key']] = dict(doc)

    for doc in docs:
        assert d[doc['key']] == doc
    
if __name__ == '__main__':
    # the --authordb and --iadb options are not in use now.
    if "--authordb" in sys.argv:
        sys.argv.remove("--authordb")
        make_author_db(sys.argv[1])
    elif "--iadb" in sys.argv:
        sys.argv.remove("--iadb")
        make_ia_db(sys.argv[1])
    else:
        main(sys.argv[1], sys.argv[2])
