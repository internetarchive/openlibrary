#!/usr/bin/python

import web, sys, codecs, locale, os
import infogami.tdb.tdb
from catalog.marc.parse import parser

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

source_id = sys.argv[1]
file_locator = sys.argv[2]
input = sys.stdin

def import_authors(authors):
    for d in authors:
        name = "a/" + d["name"]
        print name, d
        try:
            a = tdb.withName(name, site)
        except infogami.tdb.tdb.NotFound:
            a = tdb.new(name, site, author_type, d)
            a.save()
        yield a
 
i = 0
for edition_data in parser(source_id, file_locator, input):
    i += 1
    edition_name = "b/OL" + str(i) + "T"
    print edition_name, edition_data["title"]
    if 'authors' in edition_data:
        authors = edition_data["authors"]
        del edition_data["authors"]
    e = tdb.new(edition_name, site, edition_type, edition_data)
    if authors:
        e.authors = [x for x in import_authors(authors)]
    e.save()

   
