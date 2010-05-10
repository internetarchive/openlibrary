"""Library for generating and processing Open Library data dumps.

Open Library provides the following types of data dumps.

ol_cdump: Complete dump of all revisions.

Glossary:

* dump - Dump of latest revisions of all documents.
* cdump - Complete dump. Dump of all revisions of all documents.
* idump - Incremental dump. Dump of all revisions created in the given day.
"""

import simplejson
import web

import db


def print_dump(json_records):
    """Print the given json_records in the dump format.
    """
    for json in json_records:
        d = simplejson.loads(json)
        d.pop('id', None)
        json = simplejson.dumps(_process_data(d))
        print "\t".join([d['type']['key'], web.safestr(d['key']), str(d['revision']), d['last_modified']['value'], json])

def generate_cdump(data_file):
    """Generates cdump from a copy of data table.
    """
    pass
    
def generate_dump(cdump_file):
    """Generate dump from cdump."""
    pass
    
def generate_idump(day):
    """Generate incremental dump for the given day.
    
    This function must be called after initializing the database in `openlibrary.data.db` module using `setup_database` function.
    """
    rows = db.longquery("SELECT data.* FROM data, version, transaction " 
        + " WHERE data.thing_id=version.thing_id" 
        + "     AND data.revision=version.revision"
        + "     AND version.transaction_id=transaction.id"
        + "     AND transaction.created >= $day AND transaction.created < date $day + interval '1 day'",
        vars=locals())
    print_dump(row.data for chunk in rows for row in chunk)
    
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
