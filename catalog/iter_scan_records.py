from catalog.read_rc import read_rc
from catalog.infostore import get_site
from catalog.get_ia import get_from_archive
from catalog.marc.fast_parse import get_all_tag_lines
import os

site = get_site()

marc_path = '/2/pharos/marc/'

def get_data(loc):
    try:
        filename, p, l = loc.split(':')
    except ValueError:
        return None
    if not os.path.exists(marc_path + filename):
        return None
    f = open(marc_path + filename)
    f.seek(int(p))
    buf = f.read(int(l))
    f.close()
    return buf


def edition_marc(key):
    mc = list(set(v.machine_comment for v in site.versions({'key': key })))
    return [loc for loc in mc if loc]
    
key_start = len('/scan_record')
for key in site.things({'type': '/type/scan_record'}):
    assert key.startswith('/scan_record/b/')
    edition_key = key[key_start:]
    for loc in edition_marc(edition_key):
        data = get_data(loc)
        if not data or data.find('icrof') == -1:
            continue
        print "http://openlibrary.org" + edition_key
        print "http://openlibrary.org/show-marc/" + loc
        for tag, tag_line in get_all_tag_lines(data):
            if tag_line.find('icrof') == -1:
                continue
            print tag + ":", tag_line[2:-1].replace('\x1f', ' $')
        print
