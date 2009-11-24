#! /usr/bin/env python
"""Script to generate json dumps.

The script deals with 3 data formats.

1. dump of data table in OL postgres database.
2. rawdump: tab seperated file with key, type and json of page in each row
3. bookdump: dump containing only books with each property expanded. (used for solr import)

To create jsondump:
    
    1. Take dump of data table of the openlibrary database

        $ psql -c 'copy data to stdout' > data.txt

    2. Sort the dump of data table on first key. You may want to do this on a machine other than production db node.

        $ sort -k1 -S 2G data.txt > data_sorted.txt

    3. Create rawdump file.

        $ ./scripts/jsondump.py rawdump data_sorted.txt > rawdump.txt

    4. The rawdump file contains 'key', 'type' and 'json' columns. The json column should be taken to generate jsondump from rawdump.
    
        $ cut -f3 rawdump.txt > jsondump.txt
        
To generate bookdump:

    * Generate rawdump using the above procedure.
    * split types to group the dump by type. This command created type/authors.txt, type/editions.txt etc.
    
        $ ./scripts/jsondump.py split_types rawdump.txt

    * generate bookdump. (This operation is highly memory intensive).
    
        $ ./scripts/jsondump.py bookdump type/edition.txt type/author.txt type/language.txt > bookdump.txt
"""
import sys
import simplejson
import re
import time
import os

commands = {}
def command(f):
    commands[f.__name__] = f
    return f

@command
def rawdump(datafile):
    """Generates a json dump from copy of data table from OL database.
    
    Usage:
    
        $ python jsondump.py rawdump datafile > dumpfile
    """
    write_rawdump(sys.stdout, read_json(read_data_table(datafile)))

@command
def merge(dump, idump):
    """Merges a large dump with increamental dump.

        $ python jsondump.py bigdump.txt dailydump.txt > bigdump2.txt
    """
    def read(path):
        for line in xopen(path):
            key, _ = line.split("\t", 1)[0]
            yield key, line

    def do_merge():
        d = make_dict(read(idump))
        for key, line in read(dump):
            yield d.pop(key, line)
    
    sys.stdout.writelines(do_merge())

@command
def json2rawdump(jsonfile):
    """Converts a file containing json rows to rawdump format.
    """
    write_rawdump(sys.stdout, read_json(jsonfile))

@command
def split_types(rawdump):
    """Write each type of objects in separate files."""
    files = {}
    if not os.path.exists('type'):
        os.mkdir('type')

    for key, type, json in read_rawdump(rawdump):
        if type not in files:
            files[type] = open(type[1:] + '.txt', 'w')
        files[type].write("\t".join([key, type, json]))

    for t in files:
        files[t].close()

@command
def bookdump(editions_file, authors_file, languages_file):
    """Generates bookdump from rawdump.
    """
    def process():
        log("BEGIN read_authors")
        authors = make_dict((key, strip_json(json)) for key, type, json in read_rawdump(authors_file))
        languages = make_dict((key, strip_json(json)) for key, type, json in read_rawdump(languages_file))
        log("END read_authors")
        for key, type, json in read_rawdump(editions_file):
            d = simplejson.loads(strip_json(json))
            d['authors'] = [simplejson.loads(authors.get(a['key']) or '{"key": "%s"}' % a['key']) for a in d.get('authors', []) if isinstance(a, dict)]
            d['languages'] = [simplejson.loads(languages.get(a['key']) or '{"key": "%s"}' % a['key']) for a in d.get('languages', []) if isinstance(a, dict)]
            yield key, type, simplejson.dumps(d) + "\n"

    write_rawdump(sys.stdout, process())

@command
def modified(db, date):
    """Display list of modified keys on a given day.
    
        $ python jsondump.py modified dbname YYYY-MM-DD
    """
    import os
    os.system("""psql %s -t -c "select key from thing where last_modified >= '%s' and last_modified < (date '%s' + interval '1 day')" """ % (db, date, date))

@command
def help(cmd=None):
    """Displays this help."""
    action = cmd and get_action(cmd)
    if action:
        print "python jsondump.py " + cmd
        print 
        print action.__doc__
    else:
        print __doc__
        print "List of commands:"
        print

        for k in sorted(commands.keys()):
            doc = commands[k].__doc__ or " "
            print "  %-10s\t%s" % (k, doc.splitlines()[0])

def get_action(cmd):
    if cmd in commands:
        return commands[cmd]
    else:
        print >> sys.stderr, "No such command:", cmd
        return help

def listget(x, i, default=None):
    try:
        return x[i]
    except IndexError:
        return default
    
def main():
    action = get_action(listget(sys.argv, 1, "help"))
    action(*sys.argv[2:])

#---
def make_sub(d):
    """
        >>> f = make_sub(dict(a='aa', bb='b'))
        >>> f('aabbb')
        'aaaabb'
    """
    def f(a):
        return d[a.group(0)]
    rx = re.compile("|".join(map(re.escape, d.keys())))
    return lambda s: s and rx.sub(f, s)

def invert_dict(d):
    return dict((v, k) for (k, v) in d.items())

_escape_dict = {'\n': r'\n', '\r': r'\r', '\t': r'\t', '\\': r'\\'}

escape = make_sub(_escape_dict)
unescape = make_sub(invert_dict(_escape_dict))

def doctest_escape():
    r"""
        >>> escape("\n\t")
        '\\n\\t'
        >>> unescape('\\n\\t')
        '\n\t'
    """

def read_data_table(path):
    r"""Read dump of postgres data table assuming that it is sorted by first column.
    
        >>> list(read_data_table(['1\t1\tJSON-1-1\n', '1\t2\tJSON-1-2\n', '2\t1\tJSON-2-1\n']))
        ['JSON-1-2\n', 'JSON-2-1\n']
        >>> list(read_data_table(['1\t1\tJSON\\t1-1\n']))
        ['JSON\t1-1\n']
    
    """
    xthing_id = None
    xrev = 0
    xjson = ""

    for line in xopen(path):
        thing_id, rev, json = line.split("\t")
        thing_id = int(thing_id)
        rev = int(rev)
        if not xthing_id:
            xthing_id = thing_id
            xrev = rev
            xjson = json
        if xthing_id == thing_id:
            # take the json with higher rev.
            if rev > xrev:
                xrev = rev
                xjson = json
        else:
            yield unescape(xjson)
            xthing_id = thing_id
            xrev = rev
            xjson = json

    yield unescape(xjson)

def read_rawdump(file):
    r"""
        >>> list(read_rawdump(["/foo\t/type/page\tfoo-json\n", "/bar\t/type/doc\tbar-json\n"]))
        [['/foo', '/type/page', 'foo-json\n'], ['/bar', '/type/doc', 'bar-json\n']]
    """
    return (line.split("\t", 2) for line in xopen(file))

def write_rawdump(file, data):
    # assuming that newline is already present in json (column#3).
    file.writelines("%s\t%s\t%s" % row for row in data)

def read_json(file):
    r"""
        >>> list(read_json(['{"key": "/foo", "type": {"key": "/type/page"}, "title": "foo"}\n']))
        [('/foo', '/type/page', '{"key": "/foo", "type": {"key": "/type/page"}, "title": "foo"}\n')]
    """
    for json in xopen(file):
        d = simplejson.loads(json)        
        ret = (d['key'], d['type']['key'], json)
        if not all(isinstance(i, basestring) for i in ret):
            print 'not all strings:'
            print josn
        yield ret

def xopen(file):
    if isinstance(file, str):
        if file == "-":
            return sys.stdin
        elif file.endswith('.gz'):
            import gzip
            return gzip.open(file)
        else:
            return open(file)
    else:
        return file

def make_dict(items):
    return dict(items)

re_json_strip = re.compile(r', "(latest_revision|revision|id)": \d+|, "(last_modified|type|created)": {[^{}]*}')
def strip_json(json):
    """remove created, last_modified, type, etc from json."""
    return re_json_strip.sub("", json)

def log(*a):
    print >> sys.stderr, time.asctime(), " ".join(map(str, a))

def capture_stdout(f):
    import StringIO
    def g(*a):
        stdout, sys.stdout = sys.stdout, StringIO.StringIO()
        f(*a)
        out, sys.stdout = sys.stdout.getvalue(), stdout
        return out
    return g
        
@command
def test(*args):
    """Test this module.
    """
    sys.argv = args
    import doctest
    doctest.testmod()

if __name__ == "__main__":
    main()
