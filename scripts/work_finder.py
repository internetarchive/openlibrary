#!/usr/bin/python

from openlibrary.catalog.works.find_works import find_title_redirects, find_works, get_books, books_query, update_works
import sys

akey = sys.argv[1]
title_redirects = find_title_redirects(akey)
works = find_works(akey, get_books(akey, books_query(akey)), existing=title_redirects)
updated = update_works(akey, works, do_updates=True)
print 'updated works:', updated
