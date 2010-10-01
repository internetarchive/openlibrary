"""Utility to bulk import documents into Open Library database without
going through infobase API.
"""

import os
import web
import datetime
import simplejson
from collections import defaultdict

class DocumentLoader:
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
                t.rollback()
                raise
            else:
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
                                comment=comment,
                                author_id=author_id,
                                created=timestamp,
                                ip=ip)

        # add versions
        versions = [dict(transaction_id=txn_id,
                         thing_id=doc['id'],  
                         revision=doc['revision'])
                    for doc in documents]
        self.db.multiple_insert('version', versions, seqname=False)

        result = [{'key': doc['key'], 'revision': doc['revision'], 'id': doc['id']} for doc in documents]

        # insert data
        try:
            data = [dict(thing_id=doc.pop('id'),
                         revision=doc['revision'], 
                         data=simplejson.dumps(doc))
                    for doc in documents]
        except UnicodeDecodeError:
            print `doc`
            raise
        self.db.multiple_insert('data', data, seqname=False)
        return result
        
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

        WARNING: This function should not be used to change the "type" property of documents.
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


    def reindex(self, keys, tables=None):
        """Delete existing entries and add new entries to xxx_str,
        xxx_ref .. tables for the documents specified by keys.

        If optional tables argument is specified then reindex is done only for values in those tables.
        """
        return Reindexer(self.db).reindex(keys, tables)

    # this is not required anymore
    del _with_transaction

class Reindexer:
    """Utility to reindex documents."""
    def __init__(self, db):
        self.db = db

        import openlibrary.plugins.openlibrary.schema
        self.schema = openlibrary.plugins.openlibrary.schema.get_schema()
        self.noindex = set(["id", "key", "type", "type_id",
                       "revision", "latest_revision", 
                       "created", "last_modified", 
                       "permission", "child_permission"])
        self._property_cache = {}

    def reindex(self, keys, tables=None):
        """Reindex documents specified by the keys.

        If tables is specified, index is recomputed only for those tables and other tables are ignored.
        """
        t = self.db.transaction()
        
        try:
            documents = self.get_documents(keys)
            self.delete_earlier_index(documents, tables)
            self.create_new_index(documents, tables)
        except:
            t.rollback()
            raise
        else:
            t.commit()

    def get_documents(self, keys):
        """Get documents with given keys from database and add "id" and "type_id" to them.
        """
        rows = self.db.query("SELECT thing.id, thing.type, data.data" + 
                             " FROM thing, data" +
                             " WHERE data.thing_id=thing.id AND data.revision=thing.latest_revision and thing.key in $keys",
                             vars=locals())

        documents = [dict(simplejson.loads(row.data), 
                          id=row.id,
                          type_id=row.type)
                     for row in rows]
        return documents

    def delete_earlier_index(self, documents, tables=None):
        """Remove all prevous entries corresponding to the given documents"""
        all_tables = tables or set(r.relname for r in self.db.query(
                "SELECT relname FROM pg_class WHERE relkind='r'"))

        data = defaultdict(list)
        for doc in documents:
            for table in self.schema.find_tables(doc['type']['key']):
                if table in all_tables:
                    data[table].append(doc['id'])

        for table, thing_ids in data.items():
            self.db.delete(table, where="thing_id IN $thing_ids", vars=locals())
    
    def create_new_index(self, documents, tables=None):
        """Insert data in to index tables for the specified documents."""
        data = defaultdict(list)
        
        def insert(doc, name, value, ordering=None):
            # these are present in thing table. No need to index these keys
            if name in ["id", "type", "created", "last_modified", "permission", "child_permission"]:
                return
            if isinstance(value, list):
                for i, v in enumerate(value):
                    insert(doc, name, v, ordering=i)
            elif isinstance(value, dict) and 'key' not in value:
                for k, v in value.items():
                    if k == "type": # no need to index type
                        continue
                    insert(doc, name + '.' + k, v, ordering=ordering)
            else:
                datatype = self._find_datatype(value)
                table = datatype and self.schema.find_table(doc['type']['key'], datatype, name)
                # when asked to index only some tables
                if tables and table not in tables:
                    return
                if table:
                    self.prepare_insert(data[table], doc['id'], doc['type_id'], name, value, ordering=ordering)

        for doc in documents:
            for name, value in doc.items():
                insert(doc, name, value)

        # replace keys with thing ids in xxx_ref tables
        self.process_refs(data)

        # insert the data
        for table, rows in data.items():
            self.db.multiple_insert(table, rows, seqname=False)


    def get_property_id(self, type_id, name):
        if (type_id, name) not in self._property_cache:
            self._property_cache[type_id, name] = self._get_property_id(type_id, name)
        return self._property_cache[type_id, name]

    def _get_property_id(self, type_id, name):
        d = self.db.select('property', where='name=$name AND type=$type_id', vars=locals())
        if d:
            return d[0].id
        else:
            return self.db.insert('property', type=type_id, name=name)

    def prepare_insert(self, rows, thing_id, type_id, name, value, ordering=None):
        """Add data to be inserted to rows list."""
        if name in self.noindex:
            return
        elif isinstance(value, list):
            for i, v in enumerate(value):
                self.prepare_insert(rows, thing_id, type_id, name, v, ordering=i)
        else:
            rows.append(
                dict(thing_id=thing_id,
                     key_id=self.get_property_id(type_id, name),
                     value=value, 
                     ordering=ordering))

    def process_refs(self, data):
        """Convert key values to thing ids for xxx_ref tables."""
        keys = []
        for table, rows in data.items():
            if table.endswith('_ref'):
                keys += [r['value']['key'] for r in rows]

        if not keys:
            return

        thing_ids = dict((r.key, r.id) for r in self.db.query(
                "SELECT id, key FROM thing WHERE key in $keys", 
                vars=locals()))

        for table, rows in data.items():
            if table.endswith('_ref'):
                for r in rows:
                    r['value'] = thing_ids[r['value']['key']]

    def _find_datatype(self, value):
        """Find datatype of given value.

        >>> _find_datatype = Reindexer(None)._find_datatype
        >>> _find_datatype(1)
        'int'
        >>> _find_datatype('hello')
        'str'
        >>> _find_datatype({'key': '/a/OL1A'})
        'ref'
        >>> _find_datatype([{'key': '/a/OL1A'}])
        'ref'
        >>> _find_datatype({'type': '/type/text', 'value': 'foo'})
        >>> _find_datatype({'type': '/type/datetime', 'value': '2009-10-10'})
        'datetime'
        """
        if isinstance(value, int):
            return 'int'
        elif isinstance(value, basestring):
            return 'str'
        elif isinstance(value, dict):
            if 'key' in value:
                return 'ref'
            elif 'type' in value:
                return {
                    '/type/int': 'int',
                    '/type/string': 'str',
                    '/type/datetime': 'datetime'
                }.get(value['type'])
        elif isinstance(value, list):
            return value and self._find_datatype(value[0])
        else:
             return None

def _test():
    loader = DocumentLoader(db='ol')
    loader.db.printing = True
    
    n = 2

    print loader.bulk_new([dict(
                key="/b/OL%dM" % i, 
                title="book %d" % i, 
                type={"key": "/type/edition"}, 
                table_of_contents=[{"type": {"key": "/type/toc_item"}, "class": "part", "label": "test", "title": "test", "pagenum": "10"}])
            for i in range(1, n+1)], 
        comment="add books")
    
    loader.reindex(["/b/OL%dM" % i for i in range(1, n+1)])
    
if __name__ == "__main__":
    _test()
