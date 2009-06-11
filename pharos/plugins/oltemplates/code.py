import os
import web
import infogami
import urllib
import simplejson

def write(path, data):
    print 'saving', path
    path = os.path.dirname(__file__) + path
    dir = os.path.dirname(path)
    if not os.path.exists(dir):
        os.makedirs(dir)

    f = open(path, 'w')
    f.write(data)
    f.close()

def jsonget(url):
    return simplejson.loads(urllib.urlopen(url).read())

def pull_stuff(args, type, prefix, extn, body='body'):
    if args and args[0] == '--server':
        server = args[1]
        args = args[2:]
    else:
        server = 'http://openlibrary.org'

    query = {'type': type, '*': None, 'limit': 1000}
    if args:
        query['key'] = args
    else:
        query['key~'] = prefix + '/*'
        
    templates = jsonget(server + '/query.json?' + urllib.urlencode({'query': simplejson.dumps(query)}))
    for t in templates:
        name, _ = os.path.splitext(t['key'])
        write(name + extn, t[body]['value'])

@infogami.action
def pull_templates(*args):
    """Pull templates from openlibrary.org website.
    """
    pull_stuff(args, type='/type/template', prefix='/templates', extn='.html')

@infogami.action
def pull_macros(*args):
    """Pull macros from openlibrary.org website."""
    pull_stuff(args, type='/type/macro', prefix='/macros', extn='.html', body='macro')

