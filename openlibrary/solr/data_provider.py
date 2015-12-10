"""Module to provide data for solr indexer.

This module has all the logic for querying different sources for getting the
data required for solr.

Multiple data providers are supported, each is good for different use case.
"""
import web
import simplejson
import logging
from openlibrary.core import ia

logger = logging.getLogger("openlibrary.solr.data_provider")

global ia_database

def get_data_provider(type="default",ia_db=''):
    global ia_database
    ia_database = ia_db
    """Returns the data provider of given type.
    """
    if type == "default":
        return BetterDataProvider()
    elif type == "legacy":
        return LegacyDataProvider()


class DataProvider:
    """DataProvider is the interface for solr updater
    to get additional information for building solr index.

    This is an abstract class and multiple implementations are provided
    in this module.
    """
    def get_document(self, key):
        """Returns the document with specified key from the database.
        """
        raise NotImplementedError()

    def get_metadata(self, identifier):
        """Returns archive.org metadata for given identifier.
        """
        raise NotImplementedError()

    def preload_documents(self, keys):
        pass

    def preload_metadata(self, identifiers):
        pass

    def preload_editions_of_works(self, works):
        pass

    def find_redirects(self, key):
        raise NotImplementedError()

    def get_editions_of_work(self, work):
        raise NotImplementedError()        

class LegacyDataProvider(DataProvider):
    def __init__(self):
        from openlibrary.catalog.utils.query import  query_iter, withKey
        self._query_iter = query_iter
        self._withKey = withKey

    def find_redirects(self, key):
        """Returns keys of all things which are redirected to this one.
        """
        logger.info("find_redirects %s", key)
        q = {'type': '/type/redirect', 'location': key}
        return [r['key'] for r in self._query_iter(q)]

    def get_editions_of_work(self, work):
        logger.info("find_editions_of_work %s", work['key'])
        q = {'type':'/type/edition', 'works': work['key'], '*': None}
        return list(self._query_iter(q))

    def get_metadata(self, identifier):
        logger.info("find_metadata %s", identifier)
        return ia.get_metadata(identifier) 

    def get_document(self, key):
        logger.info("get_document %s", key)
        return self._withKey(key)

class BetterDataProvider(LegacyDataProvider):
    def __init__(self):
        LegacyDataProvider.__init__(self)
        # cache for documents
        self.cache = {}
        self.metadata_cache = {}

        # cache for redirects
        self.redirect_cache = {}

        self.edition_keys_of_works_cache = {}

        import infogami
        from infogami.utils import delegate

        infogami._setup()
        delegate.fakeload()

        from openlibrary.solr.process_stats import get_ia_db, get_db
        self.db = get_db()
        #self.ia_db = get_ia_db()
        self.ia_db = ia_database

    def get_metadata(self, identifier):
        """Alternate implementation of ia.get_metadata() that uses IA db directly.
        """
        logger.info("get_metadata %s", identifier)        
        self.preload_metadata([identifier])
        if self.metadata_cache.get(identifier):
            d = web.storage(self.metadata_cache[identifier])
            d.publisher = d.publisher and d.publisher.split(";")
            d.collection = d.collection and d.collection.split(";")
            d.isbn = d.isbn and d.isbn.split(";")
            d.creator = d.creator and d.creator.split(";")
            return d

    def preload_metadata(self, identifiers):
        identifiers = [id for id in identifiers if id not in self.metadata_cache]
        if not identifiers:
            return

        logger.info("preload_metadata %s", identifiers)

        fields = ('identifier, boxid, isbn, ' +
                  'title, description, publisher, creator, ' +
                  'date, collection, ' + 
                  'repub_state, mediatype, noindex')

        rows = self.ia_db.select('metadata',
            what=fields, 
            where='identifier IN $identifiers', 
            vars=locals())

        for row in rows:
            self.metadata_cache[row.identifier] = row

        for id in identifiers:
            self.metadata_cache.setdefault(id, None)

    def get_document(self, key):
        #logger.info("get_document %s", key)
        if key not in self.cache:
            self.preload_documents([key])
        if key not in self.cache:
            logger.warn("NOT FOUND %s", key)
        return self.cache.get(key) or {"key": key, "type": {"key": "/type/delete"}}

    def preload_documents(self, keys):
        identifiers = [k.replace("/books/ia:", "") for k in keys if k.startswith("/books/ia:")]
        #self.preload_ia_items(identifiers)
        re_key = web.re_compile("/(books|works|authors)/OL\d+[MWA]")

        keys2 = set(k for k in keys if re_key.match(k))
        #keys2.update(k for k in self.ia_redirect_cache.values() if k is not None)
        self.preload_documents0(keys2)
        self._preload_works()
        self._preload_authors()
        self._preload_editions()
        self._preload_metadata_of_editions()

        # for all works and authors, find redirects as they'll requested later
        keys3 = [k for k in self.cache if k.startswith("/works/") or k.startswith("/authors/")]
        self.preload_redirects(keys3)

    def preload_documents0(self, keys):
        keys = [k for k in keys if k not in self.cache]
        if not keys:
            return
        logger.info("preload_documents0 %s", keys)
        for chunk in web.group(keys, 100):
            docs = web.ctx.site.get_many(list(chunk))
            for doc in docs:
                self.cache[doc['key']] = doc.dict()

    def _preload_works(self):
        """Preloads works for all editions in the cache.
        """
        keys = []
        for doc in self.cache.values():
            if doc and doc['type']['key'] == '/type/edition' and doc.get('works'):
                keys.append(doc['works'][0]['key'])
        # print "preload_works, found keys", keys
        self.preload_documents0(keys)

    def _preload_editions(self):
        keys = []
        for doc in self.cache.values():
            if doc and doc['type']['key'] == '/type/work':
                keys.append(doc['key'])
        self.preload_editions_of_works(keys)

    def _preload_metadata_of_editions(self):
        identifiers = []
        for doc in self.cache.values():
            if doc and doc['type']['key'] == '/type/edition':
                if doc.get('ocaid'):
                    identifiers.append(doc['ocaid'])
                #source_records = doc.get("source_records", [])
                #identifiers.extend(r[len("ia:"):] for r in source_records if r.startswith("ia:"))
        self.preload_metadata(identifiers)

    def _preload_authors(self):
        """Preloads authors for all works in the cache.
        """
        keys = []
        for doc in self.cache.values():
            if doc and doc['type']['key'] == '/type/work' and doc.get('authors'):
                keys.extend(a['author']['key'] for a in doc['authors'])
            if doc and doc['type']['key'] == '/type/edition' and doc.get('authors'):
                keys.extend(a['key'] for a in doc['authors'])
        self.preload_documents0(list(set(keys)))

    def find_redirects(self, key):
        """Returns all the keys that are redirected to this.
        """
        self.preload_redirects([key])
        return self.redirect_cache[key]

    def preload_redirects(self, keys):
        keys = [k for k in keys if k not in self.redirect_cache]
        if not keys:
            return
        logger.info("preload_redirects %s", keys)
        for chunk in web.group(keys, 100):
            self._preload_redirects0(list(chunk))

    def _preload_redirects0(self, keys):
        query = {
            "type": "/type/redirect",
            "location": keys,
            "a:location": None # asking it to fill location in results
        }
        for k in keys:
            self.redirect_cache.setdefault(k, [])

        matches = web.ctx.site.things(query, details=True)
        for thing in matches:
            # we are trying to find documents that are redirecting to each of the given keys
            self.redirect_cache[thing.location].append(thing.key)

    def get_editions_of_work(self, work):
        wkey = work['key']
        self.preload_editions_of_works([wkey])
        edition_keys = self.edition_keys_of_works_cache.get(wkey, [])
        return [self.cache[k] for k in edition_keys]

    def preload_editions_of_works(self, work_keys):
        work_keys = [wkey for wkey in work_keys if wkey not in self.edition_keys_of_works_cache]
        if not work_keys:
            return
        logger.info("preload_editions_of_works %s ..", work_keys[:5])

        # Infobase doesn't has a way to do find editions of multiple works at once.
        # Using raw SQL to avoid making individual infobase queries, which is very
        # time consuming.
        key_query = ("select id from property where name='works'" +
                    " and type=(select id from thing where key='/type/edition')")

        q = ("SELECT edition.key as edition_key, work.key as work_key" +
            " FROM thing as edition, thing as work, edition_ref" +
            " WHERE edition_ref.thing_id=edition.id" +
            "   AND edition_ref.value=work.id" +
            "   AND edition_ref.key_id=({})".format(key_query) +
            "   AND work.key in $keys")
        result = self.db.query(q, vars=dict(keys=work_keys))
        for row in result:
            self.edition_keys_of_works_cache.setdefault(row.work_key, []).append(row.edition_key)

        keys = [k for _keys in self.edition_keys_of_works_cache.values()
                  for k in _keys]
        self.preload_documents0(keys)
        return
