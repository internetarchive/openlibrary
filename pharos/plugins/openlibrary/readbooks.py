"""Script to get all books from the database and print every book as python dict.

WARNING: This gets only the new books with revision=1.

Examples:
    Get first 1M books reading 5000 books at a time.
        python readbooks.py 0 1000000 5000

    Get next 1M books.
        python readbooks.py 0 1000000 5000
"""
import web
import time
import sys

def things(ids):
    ids = "(" + ", ".join([str(id) for id in ids]) + ")"
    
    # this works only for now, because the
    result = web.query(
        'SELECT thing_id, key, value, ordering FROM datum WHERE thing_id IN ' + 
        ids + 
        " ORDER BY thing_id, key, ordering")

    things = {}
    for row in result:
        t = things.setdefault(row.thing_id, {})
        if row.ordering is None:
            t[row.key] = row.value
        else:
            t.setdefault(row.key, [])
            t[row.key].append(row.value)
    return things

def books(start=0, count=100000, chunk_size=1000):
    max_revision = 2**31 - 1
    tbook = web.query("SELECT id FROM thing WHERE site_id=1 AND key='/type/edition'")[0].id

    offset = start
    limit = chunk_size

    for i in range(count/limit):
        t1 = time.time()
        #@@ this works only for new books
        result = web.query("SELECT thing.id FROM thing, datum"
            " WHERE thing.id=datum.thing_id"
            " AND datum.key='type' AND datum.value::int=$tbook AND datum.datatype=0"
            " AND begin_revision=1 AND end_revision=$max_revision"
            " ORDER BY thing.id OFFSET $offset LIMIT $limit", vars=locals())

        book_ids = [b.id for b in result]
        if not book_ids:
            break

        books = things(book_ids)
        books = [books[id] for id in book_ids]
        author_ids = set()
        for b in books:
            b.setdefault('authors', [])
            author_ids.update(b['authors'])

        authors = things(sorted(author_ids))
        for b in books:
            b['authors'] = [authors[int(id)] for id in b['authors']]
            yield b    
        offset += len(books)
        t2 = time.time()
        print >> web.debug, offset, "%f books per sec." % (len(books)/(t2-t1))

def main():
    web.config.db_parameters = dict(dbn='postgres', db='infobase_data2', host='pharosdb', user='anand', pw='')
    #web.config.db_printing = True
    web.load()

    offset = int(web.listget(sys.argv, 1, 0))
    count = int(web.listget(sys.argv, 2, 100000))
    chunk_size = int(web.listget(sys.argv, 3, 1000))
    for b in books(offset, count, chunk_size):
        print b

if __name__ == "__main__":
    main()
    
