"""Script to generate json dumps.

The script deals with 3 data formats.

1. dump of data table in OL postgres database.
2. rawdump: tab seperated file with key, type and json of page in each row
3. bookdump: dump containing only books with each property expanded. (used for solr import)

"""
import sys
import simplejson
import re

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
def bookdump(rawdump):
    """Generates bookdump from rawdump.
    """
    pass

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
    xthing_id = 1 # assuming that thing_id starts from 1 to simplify the code
    xrev = 0
    xjson = ""

    for line in xopen(path):
        thing_id, rev, json = line.split("\t")
        thing_id = int(thing_id)
        rev = int(rev)
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
        yield d['key'], d['type']['key'], json

def xopen(file):
    if isinstance(file, str):
        return open(file)
    else:
        return file

def make_dict(items):
    return dict(items)

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
    r"""Test this module.

        >>> 1 + 1
        2


    """
    sys.argv = args
    import doctest
    doctest.testmod()

if __name__ == "__main__":
    main()
