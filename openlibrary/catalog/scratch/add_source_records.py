import os, re, sys, codecs
from openlibrary.catalog.importer.db_read import get_mc

test_dir = '/home/edward/ol/test_data'

re_edition = re.compile('^/b/OL\d+M$')

for f in os.listdir(test_dir):
    key = f.replace('_', '/')
    if not re_edition.match(key):
        continue
    print key, get_mc(key)

