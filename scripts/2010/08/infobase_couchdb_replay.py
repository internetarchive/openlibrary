#! /usr/bin/env python
"""Script to reload infobase log to a couchdb database.
"""
import couchdb
import simplejson

import _init_path
from infogami.infobase.logreader import LogFile

class CouchDBReplayer:
    def __init__(self, url):
        self.db = couchdb.Database(url)
        
    def get_offset(self):
        doc = self.db.get("@offset")
        return doc and doc['offset']
        
    def set_offset(self, offset):
        doc = dict(offset=offset)
        self.db['@offset'] = self.prepare_doc(doc, "@offset")
        
    def replay(self, log):
        offset = self.get_offset()
        if offset:
            log.seek(offset)
        print offset, log.tell()
            
        for line in log:
            item = simplejson.loads(line)
            self.replay_item(item)
            
        self.set_offset(log.tell())
        
    def replay_item(self, item):
        action = item.get("action")
        m = getattr(self, "replay_" + action, None)
        return m and m(item)
        
    def replay_save(self, item):
        data = item.get('data')
        doc = data and data.get('doc')
        changeset = data.get('changeset')
        if doc and changeset:
            return self._replay_save([doc], changeset)
        
    def replay_save_many(self, item):
        data = item.get('data')
        docs = data and data.get('docs')
        changeset = data.get('changeset')
        if docs and changeset:
            return self._replay_save(docs, changeset)
        
    def _replay_save(self, docs, changeset):
        print "replaying", changeset['id']
        for doc in docs:
            self.prepare_doc(doc, doc['key'])
        self.prepare_doc(changeset, "@changes/" + changeset['id'])
        
        self.db.update(docs + [changeset])
        
    def prepare_doc(self, doc, id):
        doc['_id'] = id

        old_doc = self.db.get(id)
        if old_doc:
            doc['_rev'] = old_doc['_rev']
        return doc
        
def main(couchdb_db_url, logdir):
    replayer = CouchDBReplayer(couchdb_db_url)
    log = LogFile(logdir)
    replayer.replay(log)
    
if __name__ == '__main__':
    import sys
    main(sys.argv[1], sys.argv[2])
