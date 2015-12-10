"""Script to dump TSV of identifier,boxid,collection columns for each
archive.org text item.

All dark items are excluded.

USAGE:

    python dump-ia-items.py --host dbserver --user archive --password secret --database archive
"""

import web
import optparse

def make_parser():
    p = optparse.OptionParser()
    p.add_option("-H", "--host", default="localhost", help="database host")
    p.add_option("-u", "--user", default="archive", help="database user")
    p.add_option("-p", "--password", default="", help="database password")
    p.add_option("-d", "--database", default="", help="database name (mandatory)")
    return p    

def tabjoin(*args):
    return "\t".join((a or "").encode("utf-8") for a in args)

def dump_metadata(db):
    limit = 100000
    offset = 0

    while True:
        rows = db.select("metadata", 
                what="identifier, boxid, collection, curatestate", 
                where="mediatype='texts'", 
                limit=limit, 
                offset=offset)
        if not rows:
            break
        offset += len(rows)
        for row in rows:
            # exclude dark items
            if row.curatestate == "dark":
                continue
            print tabjoin(row.identifier, row.boxid, row.collection)

def main():
    p = make_parser()
    options, args = p.parse_args()

    if not options.database:
        p.error("Please specify a database. Try -h for help.")

    kw = {
        "dbn": "postgres",
        "host": options.host,
        "db": options.database,
        "user": options.user,
        "pw": options.password
    }

    db = web.database(**kw)
    dump_metadata(db)

if __name__ == "__main__":
    main()
