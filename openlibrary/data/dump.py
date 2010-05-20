"""Library for generating and processing Open Library data dumps.

Glossary:

* dump - Dump of latest revisions of all documents.
* cdump - Complete dump. Dump of all revisions of all documents.
* idump - Incremental dump. Dump of all revisions created in the given day.
"""

import sys
import web
import re
import time
import simplejson

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

def parse_tsv(filename):
    log("parsing", filename)
    for i, line in enumerate(open(filename)):
        if i % 1000000 == 0:
            log(i)
        yield line.strip().split("\t")

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
    
def generate_dump(cdump_file):
    """Generate dump from cdump.
    
    This is done in two passes. In pass 1, line numbers of the latest
    revisions are stored in a dictionary. In pass 2, the line numbers
    are sorted and those lines from the file are written to stdout.
    
    The cdump file is read twice, once in each pass and complexity of
    the whole operation is O(N).
    """
    # pass-1: Find the index of the rows with latest revision of each document.
    latest = {}
    for i, (type, key, revision, timestamp, json) in enumerate(read_tsv(cdump_file)):
        if latest.get(key, -1)[-1] < int(revision):
            latest[key] = (i, int(revision))
    
    # pass-2: sort the indicies and print the lines 
    rows = [index for index, rev in latest.values()]
    latest = None # free the reference
    rows.sort()
    
    file = web.iterbetter(open(cdump_file))
    sys.stdout.writelines(file[i] for i in rows)
    
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
    
def split_dump(dump_file):
    """Split dump into authors, editions and works."""
    types = ["/type/edition", "/type/author", "/type/work"]
    files = {}
    for t in types:
        tname = "dump_" + t.split("/")[-1] + "s"
        files[t] = open(dump_file.replace("dump", tname), "w")
        
    for i, line in enumerate(open(dump_file)):
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
            
    for type, key, revision, timestamp, json in parse_tsv(dump_file):
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

def read_tsv(file):
    """Read a tab seperated file and return an iterator over rows."""
    if isinstance(file, basestring):
        file = open(file)
    for line in file:
        yield line.strip().split("\t")
    
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
    elif cmd == 'split':
        split_dump(*args, **kwargs)
    elif cmd == 'index':
        make_index(*args, **kwargs)
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