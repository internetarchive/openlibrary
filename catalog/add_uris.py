#!/usr/bin/python2.5
import catalog.get_ia
from catalog.marc.fast_parse import get_all_tag_lines, get_all_subfields
from catalog.infostore import get_site
import os, sys
from catalog.read_rc import read_rc

from olwrite import Infogami

def read_uris_from_fields(fields):
    uris = []
    for tag, line in fields:
        values = {}
        for subtag, value in fast_parse.get_subfields(line, ['3', 'u']):
            if subtag in values:
                return []
            values[subtag] = value
        uris.append((values.get('u', None), values.get('3', None)))
    return uris

def read(loc, data):
    fields = fast_parse.get_tag_lines(data, ['856'])
    if not fields:
        return (None, [])
    keys = [i.key for i in site.versions({'machine_comment': loc}) if i.key.startswith('/b/')]
    if len(set(keys)) != 1:
        return (None, [])
    key = keys[0]
    if site.get(key).uris:
        return (key, [])

    return key, read_uris_from_fields(fields)

def write(key, uris):
    q = {
        'key': key,
        'uris': { 'connect': 'update_list', 'value': [ u for u, d in uris] },
        'uri_descriptions': {
            'connect': 'update_list',
            'value': [ d for u, d in uris ]
        },
    }
    ret = infogami.write(q, comment='add URIs from original MARC record')
    assert ret['status'] == 'ok'

rc = read_rc()
infogami = Infogami(rc['infogami'])
infogami.login('ImportBot', rc['ImportBot'])

site = get_site()

marc_path = '/2/pharos/marc/'
archive_id = sys.argv[1]
iter_dir = os.listdir(marc_path + archive_id)
for name in iter_dir:
    if not (name.endswith('.mrc') or name.endswith('.marc') or name.endswith('.out') or name.endswith('.dat') or name.endswith('.records.utf8')):
        continue
    full_part = archive_id + '/' + name
    print full_part
    f = open(marc_path + full_part)
    for pos, loc, data in catalog.get_ia.read_marc_file(full_part, f):
        key, uris = read(loc, data)
        if uris:
            write(key, uris)
