"""Because edition objects has volumes as back-reference instead of
property, every time an edition page is rendered an infobase query is
made to find the volumes.

This script adds all volumes as embeddable objects in the edition
itself. Please make sure you have marked /type/volume as embeddable
before running this script.

USAGE:

    python link_volumes.py http://dev.openlibrary.org
"""
import _init_path
from openlibrary.api import OpenLibrary

def take(n, items):
    def f(items):
        for i in range(n):
            yield items.next()
    return list(f(iter(items)))

def main(server):
    ol = OpenLibrary(server)
    ol.autologin()

    volumes = ol.query({'type': '/type/volume', 'limit': False, '*': None, 'edition': {'*': None}})

    volumes = dict((v['key'], v) for v in volumes)
    editions = dict((v['edition']['key'], v['edition']) for v in volumes.values() if v['edition'])

    def make_volume(v):
        d = {}
        v.pop('edition')
        v['type'] = {'key': '/type/volume'}
        for k in ['type', 'ia_id', 'volume_number']:
            if k in v:
                d[k] = v[k]
        return d

    for e in editions.values():
        e['volumes'] = []

    for v in volumes.values():
        if v.get('edition'):
            e = editions[v.get('edition')['key']]
            e['volumes'].append(make_volume(v))

    for e in editions.values():
        e['volumes'] = sorted(e['volumes'], key=lambda v: v['volume_number'])

    print 'linking volumes to %d editions' % len(editions)
    ol.save_many(editions.values(), 'link volumes')
    
if __name__ == "__main__":
    import sys
    main(sys.argv[1])
