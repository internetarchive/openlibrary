#!/usr/bin/python

from __future__ import print_function

import sys
from pprint import pprint

from openlibrary.catalog.works.find_works import (books_query, find_title_redirects,
                                                  find_works, get_books, update_works)

akey = sys.argv[1]
title_redirects = find_title_redirects(akey)
print('title_redirects:')
pprint(title_redirects)
print()

works = find_works(akey, get_books(akey, books_query(akey)), existing=title_redirects)
works = list(works)
print('works:')
pprint(works)
print()

updated = update_works(akey, works, do_updates=True)
print('updated works:')
pprint(updated)
