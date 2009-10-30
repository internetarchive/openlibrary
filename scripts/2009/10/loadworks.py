"""Script to load works fast."""
import sys
import time
import simplejson
import web
from openlibrary.utils.bulkimport import DocumentLoader, Reindexer

class WorkLoader:
    def __init__(self, **dbparams):
        self.loader = DocumentLoader(**dbparams)

        type_edition_id = self.loader.get_thing_id("/type/edition")
        self.key_id_works = Reindexer(self.loader.db).get_property_id(type_edition_id, "works")

    def load(self, filename, author="/user/ImportBot"):
        self.author = author

        for i, lines in enumerate(web.group(open(filename), 1000)):
            if i <= 20:
                continue
            if i == 30:  
                break
            t0 = time.time()
            self.load_chunk(lines)
            t1 = time.time()
            log(i, "%.3f sec" % (t1-t0))

    def load_chunk(self, lines):
        works = [eval(line) for line in lines]
        keys = self.loader.new_work_keys(len(works))

        editions = []
        for work, key in zip(works, keys):
            work['key'] = key
            work['type'] = {'key': "/type/work"}
            work['authors'] = [dict(author=a, type='/type/author_role') for a in work['authors']]
            for e in work.pop('editions'):
                if int(web.numify(e)) < 22 * 1000000:
                    editions.append(dict(key=e, works=[{"key": key}]))

        t = self.loader.db.transaction()
        try:
            modified = []
            log("adding works...")
            r_works = self.loader.bulk_new(works, comment="add works page", author=self.author)
            #log("reindexing works")
            #self.loader.reindex([d['key'] for d in modified])

            log("linking works...")
            r_editions = self.loader.bulk_update(editions, comment="link works", author=self.author)

            log("adding index...")
            key2id = dict((d['key'], d['id']) for d in r_works + r_editions)
            self.add_index(editions, key2id)

            log("done")
        except:
            t.rollback()
            raise
        else:
            t.commit()

    def add_index(self, editions, keys2id):
        rows = []
        for e in editions:
            row = dict(thing_id=keys2id[e['key']],
                    key_id=self.key_id_works,
                    value=keys2id[e['works'][0]['key']],
                    ordering=0)
            rows.append(row)
        self.loader.db.multiple_insert("edition_ref", rows, seqname=False)

def make_documents(lines):
    rows = [eval(line) for line in lines]
    return [dict(type={'key': '/type/work'},
                title=r['title'],
                authors=[dict(author=a, type='/type/author_role') for a in r['authors']])
            for r in rows]

def main(filename):
    loader = WorkLoader(db="staging", host="ia331525")
    loader.load(filename)

def log(*args):
    args = [time.asctime()] + list(args)
    sys.stdout.write(" ".join(str(a) for a in args))
    sys.stdout.write("\n")
    sys.stdout.flush()

if __name__ == "__main__":
    main(sys.argv[1])
