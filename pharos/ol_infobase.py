#!/usr/bin/env python
"""Open Library plugin for infobase.
"""
import os
import datetime
import urllib
import simplejson

import web
import schema
from infogami.infobase import config, common

def init_plugin():
    """Initialize infobase plugin."""
    from infogami.infobase import common, dbstore, server, logger
    dbstore.default_schema = schema.get_schema()

    if config.get('errorlog'):
        common.record_exception = lambda: save_error(config.errorlog, 'infobase')

    ol = server.get_site('openlibrary.org')
    ib = server._infobase

    if config.get('writelog'):
        ib.add_event_listener(logger.Logger(config.writelog))

    if ol:
        if config.get('http_listeners'):
            ol.add_trigger(None, http_notify)
        if config.get('booklog'):
            global booklogger
            booklogger = logger.Logger(config.booklog)
            ol.add_trigger('/type/edition', write_booklog)
            ol.add_trigger('/type/author', write_booklog2)
    
def write(path, data):
    dir = os.path.dirname(path)
    if not os.path.exists(dir):
        os.makedirs(dir)
    f = open(path, 'w')
    f.write(data)
    f.close()
    
def save_error(dir, prefix):
    try:
        import traceback
        traceback.print_exc()

        error = web.djangoerror()
        now = datetime.datetime.utcnow()
        path = '%s/%d-%d-%d/%s-%d%d%d.%d.html' % (dir, \
            now.year, now.month, now.day, prefix,
            now.hour, now.minute, now.second, now.microsecond)
        print >> web.debug, 'Error saved to', path
        write(path, web.safestr(error))
    except:
        import traceback
        traceback.print_exc()
    
def get_object_data(site, thing):
    """Return expanded data of specified object."""
    def expand(value):
        if isinstance(value, list):
            return [expand(v) for v in value]
        elif isinstance(value, common.Reference):
            t = site.get(value)
            return t and t._get_data()
        else:
            return value

    d = thing._get_data()
    for k, v in d.iteritems():
        # save some space by not expanding type
        if k != 'type':
            d[k] = expand(v)
    return d

booklogger = None

def write_booklog(site, old, new):
    """Log modifications to book records."""
    sitename = site.sitename
    if new.type.key == '/type/edition':
        booklogger.write('book', sitename, new.last_modified, get_object_data(site, new))
    else:
        booklogger.write('delete', sitename, new.last_modified, {'key': new.key})
        
def write_booklog2(site, old, new):
    """This function is called when any author object is changed.
    to log all books of the author if name is changed.
    """
    sitename = site.sitename
    if old and old.type.key == new.type.key == '/type/author' and old.name != new.name:
        query = {'type': '/type/edition', 'authors': new.key, 'limit': 1000}
        for d in site.things(query):
            book = site.get(d['key'])
            booklogger.write('book', sitename, new.last_modified, get_object_data(site, book))

def http_notify(site, old, new):
    """Notify listeners over http."""
    data = simplejson.dumps(new.format_data())
    for url in config.http_listeners:
        try:
            urllib.urlopen(url, data)
        except:
            print >> web.debug, "failed to send http_notify", url, new.key
            import traceback
            traceback.print_exc()

