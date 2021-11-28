import psycopg2
from timeit import default_timer as timer

from openlibrary.solr.update_work import main

if __name__ == '__main__':
    connection = psycopg2.connect(host="db", database="openlibrary")
    cursor = connection.cursor()
    cursor.execute("select key from thing")
    db_responses = cursor.fetchall()

    # We must to run main on books before authors. Books need to be indexed
    # first because the author indexing queries solr to get aggregate book data.
    for prefix in ["/books/", "/authors/"]:
        keys = [r[0] for r in db_responses if r[0].startswith(prefix)]
        start = timer()
        main(keys, ol_url="http://web:8080/", ol_config="conf/openlibrary.yml", data_provider="legacy")
        print(f"main for {prefix} took", timer() - start)
