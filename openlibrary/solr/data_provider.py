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

def get_data_provider(type="default"):
    """Returns the data provider of given type.
    """
    if type == "default":
        return BetterDataProvider()
    elif type == "legacy":
        return LegacyProvider()


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

        from openlibrary.solr.process_stats import get_ia_db, get_db
        self.db = get_db()
        self.ia_db = get_ia_db()        

    def get_metadata(self, identifier):
        return ia.get_metadata(identifier)

    def get_metadata(self, identifier):
        """Alternate implementation of ia.get_metadata() that uses IA db directly.
        """
        logger.info("get_metadata %s", identifier)        
        self.preload_metadata([identifier])
        if identifier in self.metadata_cache:
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

