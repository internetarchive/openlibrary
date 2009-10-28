"""Utility to bulk import documents into Open Library database without
going through infobase API.
"""

import os
import web
import datetime
import simplejson

class Database:
    def __init__(self, **params):
        params = params.copy()
        params.setdefault('dbn', 'postgres')
        params.setdefault('user', os.getenv('USER'))
        self.db = web.database(**params)
        self.db.printing = False
        
    def new_work_keys(self, n):
        """Returns n new works keys."""
        return ['/works/OL%dW' % i for i in self.incr_seq('type_work_seq', n)]
        
    def incr_seq(self, seqname, n):
        """Increment a sequence by n and returns the latest value of
        that sequence and returns list of n numbers.
        """
        rows = self.db.query(
            "SELECT setval($seqname, $n + (select last_value from %s)) as value" % seqname, 
            vars=locals())
        end = rows[0].value + 1 # lastval is inclusive
        begin = end - n
        return range(begin, end)

    def get_thing_ids(self, keys):
        keys = list(set(keys))
        rows = self.db.query("SELECT id, key FROM thing WHERE key in $keys", vars=locals())
        return dict((r.key, r.id) for r in rows)

    def get_thing_id(self, key):
        return self.get_thing_ids([key]).get(key)
        
    def bulk_new(self, documents, author="ImportBot", comment=None):
        """Create new documents in the database without going through
        infobase.  This approach is very fast, but this can lead to
        errors in the database if the caller is not careful.
        
        All records must contain "key" and "type"
        properties. "last_modified" and "created" properties are
        automatically added to all records.

        Entries are not added to xxx_str, xxx_ref ... tables. reindex
        method must be called separately to do that.
        """
        timestamp = datetime.datetime.utcnow()
        author_id = author and self.get_thing_id(author)

        type_ids = self.get_thing_ids(doc['type']['key'] for doc in documents)

        created = {'type': '/type/datetime', "value": timestamp.isoformat()}
        for doc in documents:
            doc['created'] = created
            doc['last_modified'] = created
            doc['revision'] = 1
            doc['latest_revision'] = 1

        t = self.db.transaction()
        try:
            # add an entry in the transaction table
            txn_id = self.db.insert('transaction',
                                 action="import",
                                 author_id=author_id,
                                 created=timestamp,
                                 ip="127.0.0.1")

            # insert things
            things = [dict(key=doc['key'], 
                           type=type_ids[doc['type']['key']], 
                           created=timestamp, 
                           last_modified=timestamp)
                      for doc in documents]
            thing_ids = self.db.multiple_insert('thing', things)

            # add versions
            versions = [dict(thing_id=thing_id, transaction_id=txn_id, revision=1)
                        for thing_id in thing_ids]
            self.db.multiple_insert('version', versions, seqname=False)

            # add data
            data = [dict(thing_id=thing_id, revision=1, data=simplejson.dumps(doc))
                    for doc, thing_id in zip(documents, thing_ids)]
            self.db.multiple_insert('data', data, seqname=False)
        except:
            t.rollback()
            raise
        else:
            t.commit()
        return [doc['key'] for key in documents]

    def bulk_update(self, docs):
        """Not yet implemented."""
        pass

    def reindex(self, keys):
        """Delete existing entries and add new entries to xxx_str,
        xxx_ref .. tables for the documents specified by keys.
        """
        pass

if __name__ == "__main__":
    db = Database(db='openlibrary')
    print db.bulk_new([dict(key=key, 
                            type={'key': '/type/work'}, 
                            title='Tom Sawyer', 
                            authors=[dict(key='/a/OL1A', type={'key': '/type/author_role'})])
                       for key in db.new_work_keys(10000)])
