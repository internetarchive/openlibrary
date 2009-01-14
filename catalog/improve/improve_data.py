from catalog.infostore import get_site
import sys, codecs

sys.stdout = codecs.getwriter('utf-8')(sys.stdout)

site = get_site()

def get_authors_by_name(name):
    return site.things({'name': name, 'type': '/type/author'})

def get_books_by_author(key):
    return site.things({'authors': key, 'type': '/type/edition'})

for author_key in get_authors_by_name(sys.argv[1]):
    print author_keys
    book_keys = get_books_by_author(author_key)
    for key in book_keys:
        t = site.get(key)
        print key, t.title
        print '  ', t.isbn_10
