"""Script to load works fast."""
import sys, os
import time
import simplejson
import web

import _init_path
from openlibrary.utils.bulkimport import DocumentLoader, Reindexer

class WorkLoader:
    def __init__(self, **dbparams):
        self.loader = DocumentLoader(**dbparams)
        self.tmpdir = "/tmp"

        # a bug in web.group has been fixed in 0.33
        assert web.__version__ == "0.33"

    def load_works(self, filename, author="/user/ImportBot"):
        self.author = author
        
        root = os.path.dirname(filename)
        editions_file = open(os.path.join(root, 'editions.txt'), 'a')
        
        try:
            for i, lines in enumerate(web.group(open(filename), 1000)):
                t0 = time.time()
                self.load_works_chunk(lines, editions_file)
                t1 = time.time()
                log(i, "%.3f sec" % (t1-t0))
        finally:
            editions_file.close()

    def load_works_chunk(self, lines, editions_file):
        authors = [eval(line) for line in lines]

        editions = {}
        for akey, works in authors:
            keys = self.loader.new_work_keys(len(works))
            for work, key in zip(works, keys):
                work['key'] = key
                work['type'] = {'key': "/type/work"}
                work['authors'] = [{'author': {'key': akey}, 'type': '/type/author_role'}]
                if 'subjects' in work:
                    del work['subjects']
                if 'toc' in work:
                    del work['toc']
                editions[key] = work.pop('editions')
                
        result = self.loader.bulk_new(works, comment="add works page", author=self.author)

        def process(result):
            for r in result:
                for e in editions[r['key']]:
                    yield "\t".join([e, r['key'], str(r['id'])]) + "\n"
        
        editions_file.writelines(process(result))
        
    def update_editions(self, filename, author="/user/ImportBot"):
        self.author = author
        
        root = os.path.dirname(filename)
        index_file = open(os.path.join(root, 'edition_ref.txt'), 'a')
            
        type_edition_id = self.loader.get_thing_id("/type/edition")
        keyid = Reindexer(self.loader.db).get_property_id(type_edition_id, "works")
        
        log("begin")
        try:
            for i, lines in enumerate(web.group(open(filename), 1000)):
                t0 = time.time()
                self.update_editions_chunk(lines, index_file, keyid)
                t1 = time.time()
                log(i, "%.3f sec" % (t1-t0))
        finally:
            index_file.close()

        log("end")
    
    def update_editions_chunk(self, lines, index_file, keyid):
        data = [line.strip().split("\t") for line in lines]
        editions = [{"key": e, "works": [{"key": w}]} for e, w, wid in data]
        result = self.loader.bulk_update(editions, comment="link works", author=self.author)
    
        def process():
            edition_map = dict((row[0], row) for row in data)
            for row in result:
                eid = row['id']
                wid = edition_map[row['key']]
                ordering = 0
                yield "\t".join(map(str, [eid, keyid, wid, ordering])) + "\n"
        index_file.writelines(process())    
        
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
    #loader = WorkLoader(db="staging", host="ia331525")
    loader = WorkLoader(db="openlibrary", host="ia331526")
#    loader.loader.db.printing = True
    loader.loader.db.printing = False
    #loader.load_works(filename)
    loader.update_editions(filename)

def log(*args):
    args = [time.asctime()] + list(args)
    sys.stdout.write(" ".join(str(a) for a in args))
    sys.stdout.write("\n")
    sys.stdout.flush()

if __name__ == "__main__":
    main(sys.argv[1])
