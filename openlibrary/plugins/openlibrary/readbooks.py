"""Script to get all books from the database and print every book as python dict.

WARNING: This gets only the new books with revision=1.

"""
import web
import time
import sys

def select(query, chunk_size=50000):
    """Selects large number of rows efficiently using cursors."""
    web.transact()
    web.query('DECLARE select_cursor CURSOR FOR ' + query)
    while True:
        result = web.query('FETCH FORWARD $chunk_size FROM select_cursor', vars=locals())
        if not result:
            break
        for r in result:
            yield r
    web.rollback()
        
def parse_datum(rows):
    thing = None
    for r in rows:
        if thing is None:
            thing = dict(id=r.thing_id)
        elif thing.get('id') != r.thing_id:
            yield thing
            thing = dict(id=r.thing_id)
        
        if r.ordering is None:
            thing[r.key] = r.value
        else:
            thing.setdefault(r.key, []).append(r.value)
            
def books(fbooks, fauthors):        
    authors = {}
    type_author = str(web.query("SELECT * FROM thing WHERE site_id=1 AND key='/type/author'")[0].id)
    type_edition = str(web.query("SELECT * FROM thing WHERE site_id=1 AND key='/type/edition'")[0].id)
    result = select("SELECT * FROM datum ORDER BY thing_id WHERE end_revision=2147483647")
    t1 = time.time()
    for i, t in enumerate(parse_datum(result)):
        if t['type'] == type_author:
            fauthors.write(str(t))
            fauthors.write("\n")
        elif t['type'] == type_edition:
            fbooks.write(str(t))
            fbooks.write("\n")

        if i and i%10000 == 0:
            t2 = time.time()
            dt = t2 - t1
            t1 = t2
            print "%d: 10000 books read in %f time. %f things/sec" % (i, dt, 10000/dt)
 
def main():
    web.config.db_parameters = dict(dbn='postgres', db='infobase_data4', host='pharosdb', user='anand', pw='')
    web.config.db_printing = True
    web.load()
    
    fbooks = open("books.txt", "w")
    fauthors = open("authors.txt", "w")
    books(fbooks, fauthors)
    fbooks.close()
    fauthors.close()

if __name__ == "__main__":
    main()
    
