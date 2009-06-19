#! /usr/bin/env python

import os
import urllib
import simplejson
import glob
import ConfigParser

import olapi
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
    elif path.startswith('/css'):
        return path[1:]
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
    elif path.startswith('css/'):
        return '/' + path
    else:
        error

def jsonget(url):
    return simplejson.loads(urllib.urlopen(url).read())

def thing2data(d):
    if d['type']['key'] == '/type/template':
        return d['body']['value']
    elif d['type']['key'] == '/type/macro':
        return d['macro']['value']
    if d['type']['key'] == '/type/rawtext':
        return d['body']['value']
    else:
        error

def update_thing(d, filename):
    data = open(filename).read()
    if d is None:
        if filename.startswith('templates'):
            d = {'type': '/type/template'}
        elif filename.startswith('macros'):
            d = {'type': '/type/macro'}
        elif filename.startswith('css'):
            d = {'type': '/type/rawtext', 'content_type': 'text/css'}
        else:
            error
        d['key'] = to_server_path(filename)

    if d['type'] == '/type/template':
        d['body'] = data
    elif d['type'] == '/type/macro':
        d['macro'] = data
    elif d['type'] == '/type/rawtext':
        d['body'] = data
    else:
        print d
        error
    return d

def olget(server, key):
    d = jsonget(server + key + '.json')
    return thing2data(d)

def get_ol(server):
    config = ConfigParser.ConfigParser()
    config.read(os.path.expanduser('~/.olrc'))

    ol = olapi.OpenLibrary(server)
    username = config.get('account', 'username')
    password = config.get('account', 'password')
    ol.login(username, password)
    return ol

def olput(server, key, filename, comment):
    print "olput", server, repr(key), repr(comment)
    def get(key):
        try:
            return ol.get(key)
        except olapi.OLError:
            return None

    ol = get_ol(server)
    d = update_thing(get(key), filename)
    print ol.save(key, d, comment=comment)

def find_files(dir):
    """Find all files in the given dir.
    """
    for dirpath, dirnames, filenames in os.walk(dir):
        for f  in filenames:
            yield os.path.join(dirpath, f)

def write(path, data):
    dir = os.path.dirname(path)
    if not os.path.exists(dir):
        os.makedirs(dir)

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
    olput(server, key, filename, comment=comment)

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
def pullall(options, *args):
    """Pull all templates/macros from openlibrary.org website.

    Usage: pullall [--server server]

    Options:
    --server server : server address (default: http://openlibrary.org)
    -O --output output: output directory (default: .)
    """
    pages = get_templates(options.server) + get_macros(options.server) + get_css(options.server)

    for d in pages:
        path = os.path.join(options.output, to_local_path(d['key']))
        print 'writing', path
        write(path, thing2data(d))

def get_templates(server):
    return jsonget(server + "/query.json?type=/type/template&key~=/templates/*&*=&limit=1000")

def get_macros(server):
    return jsonget(server + "/query.json?type=/type/macro&key~=/macros/*&*=&limit=1000")

def get_css(server):
    return jsonget(server + "/query.json?type=/type/rawtext&key~=/css/*&*=&limit=1000")

@subcommand.subcommand()
def pushall(options, *args):
    """Push all templates/macros to openlibrary.org website.

    Usage: pushall [--server server]

    Options:
    --server server : server address (default: http://openlibrary.org)
    -m [--message] message: commit message (default: push templates and macros)
    """
    pages = get_templates(options.server) + get_macros(options.server) + get_css(options.server)
    pages = olapi.unmarshal(pages)
    pages = dict((to_local_path(p['key']), p) for p in pages)

    query = []
    files = list(find_files('templates/')) + list(find_files('macros/'))
    for f in files:
        page = pages.get(f)
        d = update_thing(page and page.copy(), f)
        if page != d:
            query.append(d)

    for q in query:
        print q['key']

    get_ol(options.server).save_many(query, comment=options.message)

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

@subcommand.subcommand()
def diffall(options, *args):
    """Compare all local templates/macros with corresponding items on openlibrary.org website.

    Usage: diffall [--server server]

    Options:
    --server server : server address (default: http://openlibrary.org)
    """
    output = options.server.replace('http://', '/tmp/')

    pullall(['--server', options.server, '--output', output])
    os.system("diff -u %s/templates templates" % output)
    os.system("diff -u %s/macros macros" % output)
    os.system("rm -rf " + output)

if __name__ == "__main__":
    subcommand.main()
