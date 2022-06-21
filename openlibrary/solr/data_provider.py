"""Module to provide data for solr indexer.

This module has all the logic for querying different sources for getting the
data required for solr.

Multiple data providers are supported, each is good for different use case.
"""
import asyncio
import itertools
import logging
import re
from typing import Iterable, List, Optional, Sized

import httpx
from httpx import HTTPError
import requests
import web
from web import DB

from infogami.infobase.client import Site
from openlibrary.core import ia

logger = logging.getLogger("openlibrary.solr.data_provider")

IA_METADATA_FIELDS = ('identifier', 'boxid', 'collection', 'access-restricted-item')
OCAID_PATTERN = re.compile(r'^[^\s&#?/]+$')


def get_data_provider(type="default"):
    """Returns the data provider of given type."""
    if type == "default":
        return BetterDataProvider()
    elif type == "legacy":
        return LegacyDataProvider()


def is_valid_ocaid(ocaid: str):
    return bool(OCAID_PATTERN.match(ocaid))


def batch(items: list, max_batch_len: int):
    """
    >>> list(batch([1,2,3,4,5], 2))
    [[1, 2], [3, 4], [5]]
    >>> list(batch([], 2))
    []
    >>> list(batch([1,2,3,4,5], 3))
    [[1, 2, 3], [4, 5]]
    >>> list(batch([1,2,3,4,5], 5))
    [[1, 2, 3, 4, 5]]
    >>> list(batch([1,2,3,4,5], 6))
    [[1, 2, 3, 4, 5]]
    """
    start = 0
    while start < len(items):
        yield items[start : start + max_batch_len]
        start += max_batch_len


def batch_until_len(items: Iterable[Sized], max_batch_len: int):
    batch_len = 0
    batch: list[Sized] = []
    for item in items:
        if batch_len + len(item) > max_batch_len and batch:
            yield batch
            batch = [item]
            batch_len = len(item)
        else:
            batch.append(item)
            batch_len += len(item)
    if batch:
        yield batch


def partition(lst: list, parts: int):
    """
    >>> list(partition([1,2,3,4,5,6], 1))
    [[1, 2, 3, 4, 5, 6]]
    >>> list(partition([1,2,3,4,5,6], 2))
    [[1, 2, 3], [4, 5, 6]]
    >>> list(partition([1,2,3,4,5,6], 3))
    [[1, 2], [3, 4], [5, 6]]
    >>> list(partition([1,2,3,4,5,6], 4))
    [[1], [2], [3], [4, 5, 6]]
    >>> list(partition([1,2,3,4,5,6], 5))
    [[1], [2], [3], [4], [5, 6]]
    >>> list(partition([1,2,3,4,5,6], 6))
    [[1], [2], [3], [4], [5], [6]]
    >>> list(partition([1,2,3,4,5,6], 7))
    [[1], [2], [3], [4], [5], [6]]

    >>> list(partition([1,2,3,4,5,6,7], 3))
    [[1, 2], [3, 4], [5, 6, 7]]

    >>> list(partition([], 5))
    []
    """
    if not lst:
        return

    total_len = len(lst)
    parts = min(total_len, parts)
    size = total_len // parts

    for i in range(0, parts):
        start = i * size
        end = total_len if (i == parts - 1) else ((i + 1) * size)
        yield lst[start:end]


class DataProvider:
    """
    DataProvider is the interface for solr updater
    to get additional information for building solr index.

    This is an abstract class and multiple implementations are provided
    in this module.
    """

    def __init__(self) -> None:
        self.ia_cache: dict[str, Optional[dict]] = dict()

    @staticmethod
    async def _get_lite_metadata(ocaids: list[str], _recur_depth=0, _max_recur_depth=3):
        """
        For bulk fetch, some of the ocaids in Open Library may be bad
        and break archive.org ES fetches. When this happens, we (up to
        3 times) recursively split up the pool of ocaids to do as many
        successful sub-bulk fetches as we can and then when limit is
        reached, downstream code will fetch remaining ocaids individually
        (and skip bad ocaids)
        """
        if not ocaids or _recur_depth > _max_recur_depth:
            logger.warning(
                'Max recursion exceeded trying fetch IA data', extra={'ocaids': ocaids}
            )
            return []

        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    "https://archive.org/advancedsearch.php",
                    timeout=30,  # The default is silly short
                    params={
                        'q': f"identifier:({' OR '.join(ocaids)})",
                        'rows': len(ocaids),
                        'fl': ','.join(IA_METADATA_FIELDS),
                        'page': 1,
                        'output': 'json',
                        'save': 'yes',
                    },
                )
            r.raise_for_status()
            return r.json()['response']['docs']
        except HTTPError:
            logger.warning("IA bulk query failed")
        except (ValueError, KeyError):
            logger.warning(f"IA bulk query failed {r.status_code}: {r.json()['error']}")

        # Only here if an exception occurred
        # there's probably a bad apple; try splitting the batch
        parts = await asyncio.gather(
            *(
                DataProvider._get_lite_metadata(part, _recur_depth=_recur_depth + 1)
                for part in partition(ocaids, 6)
            )
        )
        return list(itertools.chain(*parts))

    @staticmethod
    async def _get_lite_metadata_direct(ocaid: str):
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    f"https://archive.org/metadata/{ocaid}/metadata",
                    timeout=30,  # The default is silly short
                )
            r.raise_for_status()
            response = r.json()
            if 'error' not in response:
                lite_metadata = {
                    key: response['result'][key]
                    for key in IA_METADATA_FIELDS
                    if key in response['result']
                }
                return lite_metadata
            else:
                return {
                    'error': response['error'],
                    'identifier': ocaid,
                }
        except HTTPError:
            logger.warning(f'Error fetching metadata for {ocaid}')
            return None

    async def get_document(self, key):
        """Returns the document with specified key from the database.

        :param str key: type-prefixed key (ex: /books/OL1M)
        :rtype: dict
        """
        raise NotImplementedError()

    def get_metadata(self, identifier: str):
        if identifier in self.ia_cache:
            logger.debug("IA metadata cache hit")
            return self.ia_cache[identifier]
        elif not is_valid_ocaid(identifier):
            return None
        else:
            logger.debug("IA metadata cache miss")
            return ia.get_metadata_direct(identifier)

    async def preload_documents(self, keys):
        """
        Preload a set of documents in a single request. Should make subsequent calls to
        get_document faster.

        :param list of str keys: type-prefixed keys to load (ex: /books/OL1M)
        :return: None
        """
        pass

    async def preload_metadata(self, ocaids: list[str]):
        invalid_ocaids = {ocaid for ocaid in ocaids if not is_valid_ocaid(ocaid)}
        if invalid_ocaids:
            logger.warning(f"Trying to cache invalid OCAIDs: {invalid_ocaids}")
        valid_ocaids = list(set(ocaids) - invalid_ocaids)
        batches = list(batch_until_len(valid_ocaids, 3000))
        # Start them all async
        tasks = [asyncio.create_task(self._get_lite_metadata(b)) for b in batches]
        for task in tasks:
            for doc in await task:
                self.ia_cache[doc['identifier']] = doc

        missing_ocaids = [ocaid for ocaid in valid_ocaids if ocaid not in self.ia_cache]
        missing_ocaid_batches = list(batch(missing_ocaids, 6))
        for ocaids in missing_ocaid_batches:
            # Start them all async
            tasks = [
                asyncio.create_task(self._get_lite_metadata_direct(ocaid))
                for ocaid in ocaids
            ]
            for task in tasks:
                lite_metadata = await task
                if lite_metadata:
                    self.ia_cache[lite_metadata['identifier']] = lite_metadata

    def preload_editions_of_works(self, work_keys):
        """
        Preload the editions of the provided works. Should make subsequent calls to
        get_editions_of_work faster.

        :param list of str work_keys: type-prefixed keys to work keys (ex: /works/OL1W)
        :return: None
        """
        pass

    def find_redirects(self, key):
        """
        Returns keys of all things which redirect to this one.

        :param str key: type-prefixed key
        :rtype: list of str
        """
        raise NotImplementedError()

    def get_editions_of_work(self, work):
        """

        :param dict work: work object
        :rtype: list of dict
        """
        raise NotImplementedError()

    def clear_cache(self):
        self.ia_cache.clear()


class LegacyDataProvider(DataProvider):
    def __init__(self):
        from openlibrary.catalog.utils.query import query_iter, withKey

        super().__init__()
        self._query_iter = query_iter
        self._withKey = withKey

    def find_redirects(self, key):
        """Returns keys of all things which are redirected to this one."""
        logger.info("find_redirects %s", key)
        q = {'type': '/type/redirect', 'location': key}
        return [r['key'] for r in self._query_iter(q)]

    def get_editions_of_work(self, work):
        logger.info("find_editions_of_work %s", work['key'])
        q = {'type': '/type/edition', 'works': work['key'], '*': None}
        return list(self._query_iter(q))

    async def get_document(self, key):
        logger.info("get_document %s", key)
        return self._withKey(key)


class ExternalDataProvider(DataProvider):
    """
    Only used for local env, this data provider fetches data using public OL apis
    """

    def __init__(self, ol_host: str):
        super().__init__()
        self.ol_host = ol_host

    def find_redirects(self, key: str):
        # NOT IMPLEMENTED
        return []

    def get_editions_of_work(self, work):
        resp = requests.get(
            f"http://{self.ol_host}{work['key']}/editions.json", params={'limit': 500}
        ).json()
        if 'next' in resp['links']:
            logger.warning(f"Too many editions for {work['key']}")
        return resp['entries']

    async def get_document(self, key: str):
        return requests.get(f"http://{self.ol_host}{key}.json").json()


class BetterDataProvider(LegacyDataProvider):
    def __init__(
        self,
        site: Site = None,
        db: DB = None,
    ):
        """Test with
        import web; import infogami
        from openlibrary.config import load_config
        load_config('/openlibrary/config/openlibrary.yml')
        infogami._setup()
        from infogami import config
        """
        super().__init__()

        # cache for documents
        self.cache: dict[str, dict] = {}

        # cache for redirects
        self.redirect_cache: dict[str, list[str]] = {}

        self.edition_keys_of_works_cache: dict[str, list[str]] = {}

        import infogami
        from infogami.utils import delegate

        # web.ctx might not be defined at this time -_-
        self.get_site = lambda: site or web.ctx.site

        if not db:
            infogami._setup()
            delegate.fakeload()

            from openlibrary.solr.process_stats import get_db

            self.db: DB = get_db()
        else:
            self.db = db

    async def get_document(self, key):
        # logger.info("get_document %s", key)
        if key not in self.cache:
            await self.preload_documents([key])
        if key not in self.cache:
            logger.warn("NOT FOUND %s", key)
        return self.cache.get(key) or {"key": key, "type": {"key": "/type/delete"}}

    async def preload_documents(self, keys):
        identifiers = [
            k.replace("/books/ia:", "") for k in keys if k.startswith("/books/ia:")
        ]
        # self.preload_ia_items(identifiers)
        re_key = web.re_compile(r"/(books|works|authors)/OL\d+[MWA]")

        keys2 = {k for k in keys if re_key.match(k)}
        # keys2.update(k for k in self.ia_redirect_cache.values() if k is not None)
        self.preload_documents0(keys2)
        self._preload_works()
        self._preload_authors()
        self._preload_editions()
        await self._preload_metadata_of_editions()

        # for all works and authors, find redirects as they'll requested later
        keys3 = [k for k in self.cache if k.startswith(("/works/", "/authors/"))]
        self.preload_redirects(keys3)

    def preload_documents0(self, keys):
        keys = [k for k in keys if k not in self.cache]
        if not keys:
            return
        logger.info("preload_documents0 %s", keys)
        for chunk in web.group(keys, 100):
            docs = self.get_site().get_many(list(chunk))
            for doc in docs:
                self.cache[doc['key']] = doc.dict()

    def _preload_works(self):
        """Preloads works for all editions in the cache."""
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

    async def _preload_metadata_of_editions(self):
        identifiers = []
        for doc in self.cache.values():
            if doc and doc['type']['key'] == '/type/edition':
                if doc.get('ocaid'):
                    identifiers.append(doc['ocaid'])
                # source_records = doc.get("source_records", [])
                # identifiers.extend(r[len("ia:"):] for r in source_records if r.startswith("ia:"))
        await self.preload_metadata(identifiers)

    def _preload_authors(self):
        """Preloads authors for all works in the cache."""
        keys = []
        for doc in self.cache.values():
            if doc and doc['type']['key'] == '/type/work' and doc.get('authors'):
                keys.extend(a['author']['key'] for a in doc['authors'])
            if doc and doc['type']['key'] == '/type/edition' and doc.get('authors'):
                keys.extend(a['key'] for a in doc['authors'])
        self.preload_documents0(list(set(keys)))

    def find_redirects(self, key):
        """Returns all the keys that are redirected to this."""
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
            "a:location": None,  # asking it to fill location in results
        }
        for k in keys:
            self.redirect_cache.setdefault(k, [])

        matches = self.get_site().things(query, details=True)
        for thing in matches:
            # we are trying to find documents that are redirecting to each of the given keys
            self.redirect_cache[thing.location].append(thing.key)

    def get_editions_of_work(self, work):
        wkey = work['key']
        self.preload_editions_of_works([wkey])
        edition_keys = self.edition_keys_of_works_cache.get(wkey, [])
        return [self.cache[k] for k in edition_keys]

    def preload_editions_of_works(self, work_keys):
        work_keys = [
            wkey for wkey in work_keys if wkey not in self.edition_keys_of_works_cache
        ]
        if not work_keys:
            return
        logger.info("preload_editions_of_works %s ..", work_keys[:5])

        # Infobase doesn't has a way to do find editions of multiple works at once.
        # Using raw SQL to avoid making individual infobase queries, which is very
        # time consuming.
        key_query = (
            "select id from property where name='works'"
            + " and type=(select id from thing where key='/type/edition')"
        )

        q = (
            "SELECT edition.key as edition_key, work.key as work_key"
            + " FROM thing as edition, thing as work, edition_ref"
            + " WHERE edition_ref.thing_id=edition.id"
            + "   AND edition_ref.value=work.id"
            + f"   AND edition_ref.key_id=({key_query})"
            + "   AND work.key in $keys"
        )
        result = self.db.query(q, vars=dict(keys=work_keys))
        for row in result:
            self.edition_keys_of_works_cache.setdefault(row.work_key, []).append(
                row.edition_key
            )

        keys = [k for _keys in self.edition_keys_of_works_cache.values() for k in _keys]
        self.preload_documents0(keys)
        return

    def clear_cache(self):
        super().clear_cache()
        self.cache.clear()
        self.redirect_cache.clear()
        self.edition_keys_of_works_cache.clear()
