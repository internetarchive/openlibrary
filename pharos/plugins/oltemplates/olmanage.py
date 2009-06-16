#! /usr/bin/env python

import os
import urllib
import simplejson
import glob

import subcommand

def to_local_path(path):
    """Convert path on server to local path.
    >>> to_local('/templates/site.tmpl')
    'templates/site.html'
    """
    if path.startswith('/templates'):
        return path[1:].replace('.tmpl', '.html')
    elif path.startswith('/macros'):
        return path[1:] + '.html'
    else:
        error

def to_server_path(path):
    """
    >>> to_server_path('templates/site.html')
    '/templates/site.tmpl'
    >>> to_server_path('macros/RecentChanges.html')
    '/macros/RecentChanges'
    """
    if path.startswith('templates/'):
        return '/' + path.replace('.html', '.tmpl')
    elif path.startswith('macros/'):
        return '/' + path.replace('.html', '')
    else:
        error

def jsonget(url):
    return simplejson.loads(urllib.urlopen(url).read())

def olget(server, key):
    d = jsonget(server + key + '.json')
    if d['type']['key'] == '/type/template':
        return d['body']['value']
    elif d['type']['key'] == '/type/macro':
        return d['macro']['value']
    else:
        error

def olput(server, key, data, comment):
    print "olput", server, repr(key), repr(comment)

    import olapi
    import ConfigParser

    config = ConfigParser.ConfigParser()
    config.read(os.path.expanduser('~/.olrc'))

    ol = olapi.OpenLibrary(server)
    username = config.get('account', 'username')
    password = config.get('account', 'password')
    ol.login(username, password)

    d = ol.get(key)
    print d['type']
    if d['type'] == '/type/template':
        d['body'] = data
    elif d['type'] == '/type/macro':
        d['macro'] = data
    else:
        error
    print ol.save(key, d, comment=comment)

def find_files(dir):
    """Find all files in the given dir.
    """
    for dirpath, dirnames, filenames in os.walk(dir):
        for f  in filenames:
            yield os.path.join(dirpath, f)

def write(path, data):
    f = open(path, 'w')
    f.write(data)
    f.close()

def pull_one(server, filename):
    print 'pull', filename
    key = to_server_path(filename)
    data = olget(server, key)
    write(filename, data)

def push_one(server, filename, comment=None):
    print 'push', filename
    key = to_server_path(filename)
    olput(server, key, open(filename).read(), comment=comment)

def diff_one(server, filename):
    print 'diff', filename
    key = to_server_path(filename)
    data = olget(server, key)
    write('/tmp/server-file', data)
    os.system('diff -u /tmp/server-file ' + filename)

@subcommand.subcommand()
def pull(options, *args):
    """Pull templates/macros from openlibrary.org website.

    Usage: pull [--server server] file1 file2

    Options:
    --server server : server address (default: http://openlibrary.org)
    """
    #pull_stuff(options.server, args, type='/type/template', prefix='/templates', extn='.html')
    for f in args:
        pull_one(options.server, f)

@subcommand.subcommand()
def push(options, *args):
    """Push templates/macros to openlibrary.org website.

    Usage: push [--server server] file1 file2

    Options:
    --server server : server address (default: http://openlibrary.org)
    -m [--message] message: commit message (default: )
    """
    for f in args:
        push_one(options.server, f, comment=options.message)

@subcommand.subcommand()
def diff(options, *args):
    """Compare local templates/macros with corresponding items on openlibrary.org website.

    Usage: diff [--server server] file1 file2

    Options:
    --server server : server address (default: http://openlibrary.org)
    """
    for f in args:
        diff_one(options.server, f)

if __name__ == "__main__":
    subcommand.main()
