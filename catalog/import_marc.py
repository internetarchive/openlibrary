#!/usr/bin/python

from catalog.marc.parse import parser
from time import time
import codecs
import re
import catalog.marc.MARC21

pharos = "/1/pharos/"
files = [ "marc_records_scriblio_net/part%02d.dat" % x for x in range(1,30) ]
i = 0
t0 = time()

author_cache = {}

thing = codecs.open("thing", "w", "utf-8")
version = codecs.open("version", "w", "utf-8")
datum = codecs.open("datum", "w", "utf-8")
thing_id = 169
version_id = 208
edition_type = '119'
author_type = '79'
now="2007-11-18"

re_escape = re.compile(r'[\n\r\t\0\\]')
trans = { '\n': '\\n', '\r': '\\r', '\t': '\\t', '\\': '\\\\', '\0': '', }

def esc_group(m):
    return trans[m.group(0)]
def esc(str): return re_escape.sub(esc_group, str)

def import_authors(authors):
    global thing_id, version_id
    for a in authors:
        name = unicode(a["db_name"].replace("\0", ""))
        if name in author_cache:
            yield author_cache[name]
        else:
            thing_id += 1
            version_id += 1
            thing.write("\t".join((unicode(thing_id), '2', u'a/' + name, '1')) + "\n");
            version.write("\t".join((unicode(version_id), '1', unicode(thing_id), '\N', '\N', '', now)) + "\n");
            for k in "name", "birth_date", "death_date":
                if k in a:
                    datum.write("\t".join((unicode(version_id), k, esc(unicode(a[k])), '0', '\N')) + "\n")
            datum.write("\t".join((unicode(version_id), '__type__', author_type, '1', "\N")) + "\n")
            author_cache[name] = thing_id
            yield thing_id

for file_locator in files:
    source_id = "LC"
    input = open(pharos + file_locator)
    try:
        for edition_data in parser(source_id, file_locator, input):
            i += 1
            thing_id += 1
            version_id += 1
            name = "b/OL" + str(i) + "T"
            edition_version_id = version_id
            thing.write("\t".join((unicode(thing_id), '2', name, '1')) + "\n");
            version.write("\t".join((unicode(version_id), '1', unicode(thing_id), '\N', '\N', '', now)) + "\n");
            if "authors" in edition_data:
                authors = edition_data["authors"]
                del edition_data["authors"]
            for k, v in edition_data.iteritems():
                if k != 'authors':
                    data_type = '0' # assume string
                    if k == 'publish_date':
                        data_type = '4'
                    if k == 'number_of_pages':
                        data_type = '2'
                    if isinstance(v, list):
                        for a, b in enumerate(v):
                            datum.write("\t".join((unicode(version_id), k, esc(unicode(b)), data_type, unicode(a))) + "\n")
                    else:
                        datum.write("\t".join((unicode(version_id), k, esc(unicode(v)), data_type, '\N')) + "\n")
            if authors:
                for a,b in enumerate(import_authors(authors)):
                    datum.write("\t".join((unicode(edition_version_id), 'authors', unicode(b), '1', unicode(a))) + "\n")
            datum.write("\t".join((unicode(version_id), '__type__', edition_type, '1', "\N")) + "\n")

            if not i % 1000:
                t1 = time() - t0
                print edition_data["source_record_loc"][0], name, "%.1f rec/sec" % (i/t1), edition_data["title"].encode("utf8")
    except catalog.marc.MARC21.MARC21Exn:
        pass
    input.close()

thing.close()
version.close()
datum.close()
