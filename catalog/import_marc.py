#!/usr/bin/python

import web, sys, codecs, locale, os
import infogami.tdb.tdb
from catalog.marc.parse import parser
from time import time
import psycopg2

#encoding = locale.getdefaultlocale()[1]
#sys.stdout = codecs.getwriter(encoding)(sys.stdout)

def fix_unicode (edition):
    for k, v in edition.iteritems():
        if isinstance(v, unicode):
            edition[k] = v.encode('utf8').replace("\0", "")
        elif isinstance(v, list):
            for i in range(len(v)):
                if isinstance(v[i], unicode):
                    v[i] = v[i].encode('utf8').replace("\0", "")
    return edition

pharos = "/1/pharos/"
files = [ "marc_records_scriblio_net/part%02d.dat" % x for x in range(1,30) ]
seen_author = {}

dbname = os.getenv("PHAROS_DBNAME")
dbuser = os.getenv("PHAROS_DBUSER")
dbpass = os.getenv("PHAROS_DBPASS")

web.config.db_parameters = dict(dbn='postgres', db=dbname, user=dbuser)
if dbpass:
    web.config.db_parameters['pw'] = dbpass
web.db._hasPooling = False
web.config.db_printing = False
web.load()

tdb = infogami.tdb.tdb.SimpleTDBImpl ()
tdb.setup ()

site = tdb.withName("openlibrary.org", tdb.root)
edition_type = tdb.withName("type/edition", site)
author_type = tdb.withName("type/author", site)

def import_authors(authors):
    for d in authors:
        name = "a/" + d["db_name"].encode('utf8').replace("\0", "")
        if name in seen_author:
            a = tdb.withName(name, site)
        else:
            del d["db_name"]
            a = tdb.new(name, site, author_type, fix_unicode(d))
            try:
                a.save()
            except psycopg2.IntegrityError:
                print name, fix_unicode(d)
                raise
            seen_author[name] = 1
        yield a
 
i = 0

t0 = time()

for file_locator in files:
    print file_locator
    source_id = "LC"
    input = open(pharos + file_locator)
    for edition_data in parser(source_id, file_locator, input):
        i += 1
        edition_name = "b/OL" + str(i) + "T"
        if not i % 1000:
            t1 = time() - t0
            print edition_data["source_record_loc"][0], edition_name, "%.1f rec/sec" % (i/t1), edition_data["title"].encode("utf8")
        authors = []
        if 'authors' in edition_data:
            authors = edition_data["authors"]
            del edition_data["authors"]
        e = tdb.new(edition_name, site, edition_type, fix_unicode(edition_data))
        if authors:
            e.authors = [x for x in import_authors(authors)]
        e.save()
    input.close()
