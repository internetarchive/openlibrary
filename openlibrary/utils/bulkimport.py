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

    def _with_transaction(f):
        """Decorator to run a method in a transaction.
        """
        def g(self, *a, **kw):
            t = self.db.transaction()
            try:
                value = f(self, *a, **kw)
            except:
                print 'rollback'
                t.rollback()
                raise
            else:
                print 'commit'
                t.commit()
            return value
        return g

    def bulk_new(self, documents, author="/user/ImportBot", comment=None):
        """Create new documents in the database without going through
        infobase.  This approach is very fast, but this can lead to
        errors in the database if the caller is not careful.
        
        All records must contain "key" and "type"
        properties. "last_modified" and "created" properties are
        automatically added to all records.

        Entries are not added to xxx_str, xxx_ref ... tables. reindex
        method must be called separately to do that.
        """
        return self._bulk_new(documents, author, comment)

    @_with_transaction
    def _bulk_new(self, documents, author, comment):
        timestamp = datetime.datetime.utcnow()
        type_ids = self.get_thing_ids(doc['type']['key'] for doc in documents)

        # insert things
        things = [dict(key=doc['key'], 
                       type=type_ids[doc['type']['key']], 
                       created=timestamp, 
                       last_modified=timestamp)
                  for doc in documents]
        thing_ids = self.db.multiple_insert('thing', things)

        # prepare documents
        created = {'type': '/type/datetime', "value": timestamp.isoformat()}
        for doc, thing_id in zip(documents, thing_ids):
            doc['id'] = thing_id
            doc['revision'] = 1
            doc['latest_revision'] = 1
            doc['created'] = created
            doc['last_modified'] = created

        # insert data
        return self._insert_data(documents, author=author, timestamp=timestamp, comment=comment)

    def _insert_data(self, documents, author, timestamp, comment, ip="127.0.0.1"):
        """Add entries in transaction and version tables for inseting
        above documents.

        It is assumed that correct value of id, revision and
        last_modified is already set in all documents.
        """
        author_id = author and self.get_thing_id(author)

        # add an entry in the transaction table
        txn_id = self.db.insert('transaction',
                                 action="import",
                                 author_id=author_id,
                                 created=timestamp,
                                 ip=ip)

        # add versions
        versions = [dict(transaction_id=txn_id,
                         thing_id=doc['id'],  
                         revision=doc['revision'])
                    for doc in documents]
        self.db.multiple_insert('version', versions, seqname=False)

        # insert data
        data = [dict(thing_id=doc.pop('id'),
                     revision=doc['revision'], 
                     data=simplejson.dumps(doc))
                for doc in documents]
        self.db.multiple_insert('data', data, seqname=False)

        return [{'key': doc['key'], 'revision': doc['revision']} for doc in documents]
        
    def bulk_update(self, documents, author='/user/ImportBot', comment=None):
        """Update existing documents in the database. 

        When adding new properties, it is sufficient to specify key and
        new properties.

        db.bulk_update([
            {'key': '/b/OL1M', 'work': {'key': '/works/OL1W'}}
            {'key': '/b/OL2M', 'work': {'key': '/works/OL2M'}}],
            comment="link works")

        When updating an existing property, it sufficient to specify key and new value of that property.

        db.bulk_update([
            {'key': '/b/OL1M', 'title': 'New title'}],
            comment="unicode normalize titles")

        When append new value to an existing property, entire list must be provied.

        db.bulk_update([{
                'key': '/a/OL1A', 
                'links': ['http://en.wikipedia.org/wiki/Foo', 'http://de.wikipedia.org/wiki/Foo']
            }, comment="add german wikipedia links")
        """
        return self._bulk_update(documents, author, comment)

    @_with_transaction
    def _bulk_update(self, documents, author, comment):
        timestamp = datetime.datetime.utcnow()

        keys = [doc['key'] for doc in documents]

        # update latest_revision and last_modified in thing table
        self.db.query("UPDATE thing" + 
                      " SET last_modified=$timestamp, latest_revision=latest_revision+1" + 
                      " WHERE key IN $keys",
                      vars=locals())

        # fetch the current data
        rows = self.db.query("SELECT thing.id, thing.key, thing.created, thing.latest_revision, data.data" + 
                             " FROM thing, data" +
                             " WHERE data.thing_id=thing.id AND data.revision=thing.latest_revision-1 and thing.key in $keys",
                             vars=locals())

        rows = dict((r.key, r) for r in rows)
        last_modified = {'type': '/type/datetime', 'value': timestamp.isoformat()}
        def prepare(doc):
            """Takes the existing document from db, update it with doc
            and add revision, latest_revision, last_modified
            properties.
            """
            r = rows[doc['key']]
            d = simplejson.loads(r.data)
            d.update(doc, 
                     revision=r.latest_revision,
                     latest_revision=r.latest_revision,
                     last_modified=last_modified,
                     id=r.id)
            return d

        documents = [prepare(doc) for doc in documents]
        return self._insert_data(documents, author=author, timestamp=timestamp, comment=comment)

    def reindex(self, keys):
        """Delete existing entries and add new entries to xxx_str,
        xxx_ref .. tables for the documents specified by keys.
        """
        pass

    del _with_transaction

def _test():
    db = Database(db='openlibrary')
    print db.bulk_new([dict(key="/b/OL%dM" % i, title="book %d" % i, type={"key": "/type/edition"}) for i in range(1, 101)], comment="add books")
    print db.bulk_new([dict(key="/a/OL%dA" % i, name="author %d" % i, type={"key": "/type/author"}) for i in range(1, 101)], comment="add authors")
    print db.bulk_update([dict(key="/b/OL%dM" % i, authors=[{"key": "/a/OL%dA" % i}]) for i in range(1, 101)], comment="link authors")

    """
    print db.bulk_new([dict(key=key, 
                            type={'key': '/type/work'}, 
                            title='Tom Sawyer', 
                            authors=[dict(key='/a/OL1A', type={'key': '/type/author_role'})])
                       for key in db.new_work_keys(10000)])
   """
    

if __name__ == "__main__":
    _test()
