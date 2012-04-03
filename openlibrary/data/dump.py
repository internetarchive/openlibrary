"""Library for generating and processing Open Library data dumps.

Glossary:

* dump - Dump of latest revisions of all documents.
* cdump - Complete dump. Dump of all revisions of all documents.
* idump - Incremental dump. Dump of all revisions created in the given day.
"""

import sys, os
import web
import re
import time
import simplejson
import itertools
import gzip

import db

def print_dump(json_records, filter=None):
    """Print the given json_records in the dump format.
    """
    for i, json in enumerate(json_records):
        if i % 1000000 == 0:
            log(i)
        d = simplejson.loads(json)
        d.pop('id', None)
        d = _process_data(d)
        
        key = web.safestr(d['key'])
        type = d['type']['key']
        timestamp = d['last_modified']['value']
        json = simplejson.dumps(d)
        
        # skip user and admin pages
        if key.startswith("/people/") or key.startswith("/admin/"):
            continue
        
        # skip obsolete pages. Obsolete pages include volumes, scan_records and users marked as spam.
        if key.startswith("/b/") or key.startswith("/scan") or key.startswith("/old/") or not key.startswith("/"):
            continue
        
        if filter and filter(d) is False:
            continue
            
        print "\t".join([type, key, str(d['revision']), timestamp, json])
        
def read_data_file(filename):
    for line in open(filename):
        thing_id, revision, json = line.strip().split("\t")
        yield pgdecode(json)
        
def log(*args):
    print >> sys.stderr, time.asctime(), " ".join(str(a) for a in args)
    
def xopen(path, mode='r'):
    if path.endswith(".gz"):
        return gzip.open(path, mode)
    else:
        return open(path, mode)

def read_tsv(file, strip=True):
    """Read a tab seperated file and return an iterator over rows."""    
    log("reading", file)
    if isinstance(file, basestring):
        file = xopen(file)
        
    for i, line in enumerate(file):
        if i % 1000000 == 0:
            log(i)
        if strip:
            line = line.strip()
        yield line.split("\t")

def generate_cdump(data_file, date=None):
    """Generates cdump from a copy of data table.
    If date is specified, only revisions created on or before that date will be considered.
    """
    
    # adding Z to the date will make sure all the timestamps of that day are less than date.
    #
    #   >>> "2010-05-17T10:20:30" < "2010-05-17"
    #   False
    #   >>> "2010-05-17T10:20:30" < "2010-05-17Z"
    #   True
    filter = date and (lambda doc: doc['last_modified']['value'] < date + "Z")
    
    print_dump(read_data_file(data_file), filter=filter)
        
def sort_dump(dump_file=None, tmpdir="/tmp/", buffer_size="1G"):
    """Sort the given dump based on key."""
    tmpdir = os.path.join(tmpdir, "oldumpsort")
    if not os.path.exists(tmpdir):
        os.makedirs(tmpdir)
        
    M = 1024*1024
    
    filenames = [os.path.join(tmpdir, "%02x.txt.gz" % i) for i in range(256)]
    files = [gzip.open(f, 'w') for f in filenames]
    
    if dump_file is None:
        stdin = sys.stdin
    else:
        stdin = xopen(dump_file)
    
    # split the file into 256 chunks using hash of key
    log("splitting", dump_file)
    for i, line in enumerate(stdin):
        if i % 1000000 == 0:
            log(i)
        
        type, key, revision, timestamp, json = line.strip().split("\t")
        findex = hash(key) % 256
        files[findex].write(line)
        
    for f in files:
        f.flush()
        f.close()
    files = []
        
    for fname in filenames:
        log("sorting", fname)
        status = os.system("gzip -cd %(fname)s | sort -S%(buffer_size)s -k2,3" % locals())
        if status != 0:
            raise Exception("sort failed with status %d" % status)
    
def pmap(f, tasks):
    """Run tasks parallelly."""
    try:
        from subprocess import Pool
        
        from multiprocessing import Pool
        r = pool.map_async(f, tasks, callback=results.append)
        r.wait() # Wait on the results
        
    except ImportError:
        Pool = None
    
def generate_dump(cdump_file=None):
    """Generate dump from cdump.
    
    The given cdump must be sorted by key.
    """   
    def process(data):
        revision = lambda cols: int(cols[2])
        for key, rows in itertools.groupby(data, key=lambda cols: cols[1]):
            row = max(rows, key=revision)
            yield row
            
    tjoin = "\t".join        
    data = read_tsv(cdump_file or sys.stdin, strip=False)
    # group by key and find the max by revision
    sys.stdout.writelines(tjoin(row) for row in process(data))
        
def generate_idump(day, **db_parameters):
    """Generate incremental dump for the given day.
    """
    db.setup_database(**db_parameters)
    rows = db.longquery("SELECT data.* FROM data, version, transaction " 
        + " WHERE data.thing_id=version.thing_id" 
        + "     AND data.revision=version.revision"
        + "     AND version.transaction_id=transaction.id"
        + "     AND transaction.created >= $day AND transaction.created < date $day + interval '1 day'"
        + " ORDER BY transaction.created",
        vars=locals(), chunk_size=10000)
    print_dump(row.data for chunk in rows for row in chunk)
    
def split_dump(dump_file=None, format="oldump_%s.txt"):
    """Split dump into authors, editions and works."""
    types = ["/type/edition", "/type/author", "/type/work", "/type/redirect"]
    files = {}
    for t in types:
        tname = t.split("/")[-1] + "s"
        files[t] = open(format % tname, "w", 5*1024*1024)
        
    if dump_file is None:
        stdin = sys.stdin
    else:
        stdin = xopen(dump_file)
        
    for i, line in enumerate(stdin):
        if i % 1000000 == 0:
            log(i)
        type, rest = line.split("\t", 1)
        if type in files:
            files[type].write(line)
            
    for f in files.values():
        f.close()
    
def make_index(dump_file):
    """Make index with "path", "title", "created" and "last_modified" columns."""
    
    from openlibrary.plugins.openlibrary.processors import urlsafe
            
    for type, key, revision, timestamp, json in read_tsv(dump_file):
        data = simplejson.loads(json)
        if type == '/type/edition' or type == '/type/work':
            title = data.get('title', 'untitled')
            path = key + '/' + urlsafe(title)
        elif type == '/type/author':
            title = data.get('name', 'unnamed')
            path = key + '/' + urlsafe(title)
        else:
            title = data.get('title', key)
            path = key
            
        title = title.replace("\t", " ")
        
        if 'created' in data:
            created = data['created']['value']
        else:
            created = "-"
        print "\t".join([web.safestr(path), web.safestr(title), created, timestamp])
        
def make_bsddb(dbfile, dump_file):
    import bsddb 
    db = bsddb.btopen(dbfile, 'w', cachesize=1024*1024*1024)
    
    from infogami.infobase.utils import flatten_dict
    
    indexable_keys = set([
        "authors.key",  "works.key", # edition
        "authors.author.key", "subjects", "subject_places", "subject_people", "subject_times" # work
    ])
    for type, key, revision, timestamp, json in read_tsv(dump_file):
        db[key] = json
        d = simplejson.loads(json)
        index = [(k, v) for k, v in flatten_dict(d) if k in indexable_keys]
        for k, v in index:
            k = web.rstrips(k, ".key")
            if k.startswith("subject"):
                v = '/' + v.lower().replace(" ", "_")
                
            dbkey  = web.safestr('by_%s%s' % (k, v))
            if dbkey in db:
                db[dbkey] = db[dbkey] + " " + key
            else:
                db[dbkey] = key
    db.close()
    log("done")

def _process_key(key):
    mapping = (
        "/l/", "/languages/",
        "/a/", "/authors/",
        "/b/", "/books/",
        "/user/", "/people/"
    )
    for old, new in web.group(mapping, 2):
        if key.startswith(old):
            return new + key[len(old):]
    return key

def _process_data(data):
    """Convert keys from /a/, /b/, /l/ and /user/ to /authors/, /books/, /languages/ and /people/ respectively.
    """
    if isinstance(data, list):
        return [_process_data(d) for d in data]
    elif isinstance(data, dict):
        if 'key' in data:
            data['key'] = _process_key(data['key'])
            
        # convert date to ISO format
        if 'type' in data and data['type'] == '/type/datetime':
            data['value'] = data['value'].replace(' ', 'T')
            
        return dict((k, _process_data(v)) for k, v in data.iteritems())
    else:
        return data

def _make_sub(d):
    """Make substituter.

        >>> f = _make_sub(dict(a='aa', bb='b'))
        >>> f('aabbb')
        'aaaabb'
    """
    def f(a):
        return d[a.group(0)]
    rx = re.compile("|".join(map(re.escape, d.keys())))
    return lambda s: s and rx.sub(f, s)

def _invert_dict(d):
    return dict((v, k) for (k, v) in d.items())

_pgencode_dict = {'\n': r'\n', '\r': r'\r', '\t': r'\t', '\\': r'\\'}
_pgencode = _make_sub(_pgencode_dict)
_pgdecode = _make_sub(_invert_dict(_pgencode_dict))

def pgencode(text):
    """Reverse of pgdecode."""
    return _pgdecode(text)

def pgdecode(text):
    r"""Decode postgres encoded text.
        
        >>> pgdecode('\\n')
        '\n'
    """
    return _pgdecode(text)

def main(cmd, args):
    """Command Line interface for generating dumps.
    """
    iargs = iter(args)

    args = []
    kwargs = {}
    
    for a in iargs:
        if a.startswith('--'):
            name = a[2:].replace("-", "_")
            value = iargs.next()
            kwargs[name] = value
        else:
            args.append(a)
    
    if cmd == 'cdump':
        generate_cdump(*args, **kwargs)
    elif cmd == 'dump':
        generate_dump(*args, **kwargs)
    elif cmd == 'idump':
        generate_idump(*args, **kwargs)
    elif cmd == 'sort':
        sort_dump(*args, **kwargs)
    elif cmd == 'split':
        split_dump(*args, **kwargs)
    elif cmd == 'index':
        make_index(*args, **kwargs)
    elif cmd == 'bsddb':
        make_bsddb(*args, **kwargs)
    elif cmd == "solrdump":
        import solr
        solr.generate_dump(*args, **kwargs)
    elif cmd == 'sitemaps':
        from sitemap import generate_sitemaps
        generate_sitemaps(*args, **kwargs)
    elif cmd == 'htmlindex':
        from sitemap import generate_html_index
        generate_html_index(*args, **kwargs)
    else:
        print >> sys.stderr, "Unknown command:", cmd

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
