from __future__ import division

import asyncio
import itertools
import json
import re
from typing import Awaitable, List, Iterable, Literal, Sized

import httpx
from httpx import HTTPError
from configparser import ConfigParser
import logging
import time
import uuid
from collections import namedtuple

import psycopg2

from openlibrary.core import ia
from openlibrary.solr import update_work
from openlibrary.solr.data_provider import DataProvider
from openlibrary.solr.update_work import load_configs, update_keys

logger = logging.getLogger("openlibrary.solr-builder")
LITE_METADATA_FIELDS = ('identifier', 'boxid', 'collection')
OCAID_PATTERN = re.compile(r'^[^\s&#?/]+$')


def is_valid_ocaid(ocaid: str):
    return bool(OCAID_PATTERN.match(ocaid))


def config_section_to_dict(config_file, section):
    """
    Read a config file's section as a dict

    :param str config_file: filename of config file
    :param str section: section to pull data from
    :return: dict of key value pairs
    :rtype: dict
    """
    config = ConfigParser()
    config.read(config_file)
    result = {key: config.get(section, key) for key in config.options(section)}
    return result


def partition(lst: List, parts: int):
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


def batch_until_len(items: Iterable[Sized], max_batch_len: int):
    batch_len = 0
    batch = []  # type: List[Sized]
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


def batch(items: List, max_batch_len: int):
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
        yield items[start:start + max_batch_len]
        start += max_batch_len


def safeget(func):
    """
    >>> safeget(lambda: {}['foo'])
    >>> safeget(lambda: {}['foo']['bar'][0])
    >>> safeget(lambda: {'foo': []}['foo'][0])
    >>> safeget(lambda: {'foo': {'bar': [42]}}['foo']['bar'][0])
    42
    """
    try:
        return func()
    except KeyError:
        return None
    except IndexError:
        return None


class LocalPostgresDataProvider(DataProvider):
    """
    This class uses a local postgres dump of the database.
    """

    def __init__(self, db_conf_file):
        """
        :param str db_conf_file: file to DB config with [postgres] section
        """
        self._db_conf = config_section_to_dict(db_conf_file, "postgres")
        self._conn = None  # type: psycopg2._psycopg.connection
        self.cache = dict()
        self.cached_work_editions_ranges = []
        self.ia_cache = dict()
        self.ia = None

    def __enter__(self):
        """
        :rtype: LocalPostgresDataProvider
        """
        self._conn = psycopg2.connect(**self._db_conf)
        return self

    def __exit__(self, type, value, traceback):
        self.clear_cache()
        self._conn.close()

    def query_all(self, query, cache_json=False):
        """

        :param str query:
        :param bool cache_json:
        :rtype: list
        """
        cur = self._conn.cursor()
        cur.execute(query)
        rows = cur.fetchall()
        cur.close()

        if rows:
            if cache_json:
                self.cache.update({row[0]: row[1] for row in rows})
            return rows
        else:
            return []

    def query_iter(self, query, size=20):
        cur = self._conn.cursor()
        cur.execute(query)

        while True:
            rows = cur.fetchmany(size)
            if not rows:
                break
            for row in rows:
                yield row

        cur.close()

    def query_batched(self, query, size, cursor_name=None, cache_json=False):
        """
        :param str query:
        :param int size:
        :param str or None cursor_name: if wanting to use a specific cursor
        :param bool cache_json: Requires the select statement to be "Key", "JSON"
        :return:
        """
        # Not sure if this name needs to be unique
        cursor_name = cursor_name \
            or 'solr_builder_server_side_cursor_' + uuid.uuid4().hex
        cur = self._conn.cursor(name=cursor_name)
        cur.itersize = size
        cur.execute(query)

        while True:
            rows = cur.fetchmany(size)
            if not rows:
                break
            else:
                if cache_json:
                    self.cache.update({row[0]: row[1] for row in rows})
                yield rows

        cur.close()

    @staticmethod
    async def _get_lite_metadata(ocaids, _recur_depth=0, _max_recur_depth=3):
        """
        For bulk fetch, some of the ocaids in Open Library may be bad
        and break archive.org ES fetches. When this happens, we (up to
        3 times) recursively split up the pool of ocaids to do as many
        successful sub-bulk fetches as we can and then when limit is
        reached, downstream code will fetch remaining ocaids individually
        (and skip bad ocaids)
        """
        if not ocaids or _recur_depth > _max_recur_depth:
            logger.warning('Max recursion exceeded trying fetch IA data', extra={
                'ocaids': ocaids
            })
            return []

        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    "https://archive.org/advancedsearch.php",
                    timeout=30,  # The default is silly short
                    params={
                        'q': f"identifier:({' OR '.join(ocaids)})",
                        'rows': len(ocaids),
                        'fl': ','.join(LITE_METADATA_FIELDS),
                        'page': 1,
                        'output': 'json',
                        'save': 'yes',
                    }
                )
            r.raise_for_status()
            return r.json()['response']['docs']
        except HTTPError:
            logger.warning("IA bulk query failed")
        except (ValueError, KeyError):
            logger.warning(f"IA bulk query failed {r.status_code}: {r.json()['error']}")

        # Only here if an exception occurred
        # there's probably a bad apple; try splitting the batch
        parts = await asyncio.gather(*(
            LocalPostgresDataProvider._get_lite_metadata(
                part, _recur_depth=_recur_depth + 1)
            for part in partition(ocaids, 6)
        ))
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
                    for key in LITE_METADATA_FIELDS if key in response['result']
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

    async def cache_ia_metadata(self, ocaids: List[str]):
        invalid_ocaids = set(ocaid for ocaid in ocaids if not is_valid_ocaid(ocaid))
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
                for ocaid in ocaids]
            for task in tasks:
                lite_metadata = await task
                if lite_metadata:
                    self.ia_cache[lite_metadata['identifier']] = lite_metadata

    def cache_edition_works(self, lo_key, hi_key):
        q = """
            SELECT works."Key", works."JSON"
            FROM "test" editions
            INNER JOIN test works
                ON editions."JSON" -> 'works' -> 0 ->> 'key' = works."Key"
            WHERE editions."Type" = '/type/edition'
                AND '%s' <= editions."Key" AND editions."Key" <= '%s'
        """ % (lo_key, hi_key)
        self.query_all(q, cache_json=True)

    def cache_work_editions(self, lo_key, hi_key):
        q = """
            SELECT "Key", "JSON"
            FROM "test"
            WHERE "Type" = '/type/edition'
                AND '%s' <= "JSON" -> 'works' -> 0 ->> 'key'
                AND "JSON" -> 'works' -> 0 ->> 'key' <= '%s'
        """ % (lo_key, hi_key)
        self.query_all(q, cache_json=True)
        self.cached_work_editions_ranges.append((lo_key, hi_key))

    def cache_edition_authors(self, lo_key, hi_key):
        q = """
            SELECT authors."Key", authors."JSON"
            FROM "test" editions
            INNER JOIN test works
                ON editions."JSON" -> 'works' -> 0 ->> 'key' = works."Key"
            INNER JOIN test authors
                ON works."JSON" -> 'authors' -> 0 -> 'author' ->> 'key' = authors."Key"
            WHERE editions."Type" = '/type/edition'
                AND editions."JSON" -> 'works' -> 0 ->> 'key' IS NULL
                AND '%s' <= editions."Key" AND editions."Key" <= '%s'
        """ % (lo_key, hi_key)
        self.query_all(q, cache_json=True)

    def cache_work_authors(self, lo_key, hi_key):
        # Cache upto first five authors
        q = """
            SELECT authors."Key", authors."JSON"
            FROM "test" works
            INNER JOIN "test" authors ON (
                works."JSON" -> 'authors' -> 0 -> 'author' ->> 'key' = authors."Key" OR
                works."JSON" -> 'authors' -> 1 -> 'author' ->> 'key' = authors."Key" OR
                works."JSON" -> 'authors' -> 2 -> 'author' ->> 'key' = authors."Key" OR
                works."JSON" -> 'authors' -> 3 -> 'author' ->> 'key' = authors."Key" OR
                works."JSON" -> 'authors' -> 4 -> 'author' ->> 'key' = authors."Key"
            )
            WHERE works."Type" = '/type/work'
            AND '%s' <= works."Key" AND works."Key" <= '%s'
        """ % (lo_key, hi_key)
        self.query_all(q, cache_json=True)

    async def cache_cached_editions_ia_metadata(self):
        ocaids = list(set(
            doc['ocaid'] for doc in self.cache.values()
            if 'ocaid' in doc))
        await self.cache_ia_metadata(ocaids)

    def find_redirects(self, key):
        """Returns keys of all things which redirect to this one."""
        logger.debug("find_redirects %s", key)
        q = """
        SELECT "Key" FROM test
        WHERE "Type" = '/type/redirect' AND "JSON" ->> 'location' = '%s'
        """ % key
        return [r[0] for r in self.query_iter(q)]

    def get_editions_of_work_direct(self, work):
        q = """
        SELECT "JSON" FROM test
        WHERE "Type" = '/type/edition' AND "JSON" -> 'works' -> 0 ->> 'key' = '%s'
        """ % work['key']
        return [r[0] for r in self.query_iter(q)]

    def get_editions_of_work(self, work):
        # They should all be cached...
        cache_hit = any(
            lo <= work['key'] <= hi
            for (lo, hi) in self.cached_work_editions_ranges)
        if cache_hit:
            return [
                doc for doc in self.cache.values()
                if (doc['type']['key'] == '/type/edition' and
                    safeget(lambda: doc['works'][0]['key'] == work['key']))
            ]
        else:
            return self.get_editions_of_work_direct(work)

    def get_metadata(self, identifier):
        if identifier in self.ia_cache:
            logger.debug("IA metadata cache hit")
            return self.ia_cache[identifier]
        elif not is_valid_ocaid(identifier):
            return None
        else:
            logger.debug("IA metadata cache miss")
            return ia.get_metadata_direct(identifier)

    def get_document(self, key):
        if key in self.cache:
            logger.debug("get_document cache hit %s", key)
            return self.cache[key]

        logger.debug("get_document cache miss %s", key)

        q = """
        SELECT "JSON" FROM test
        WHERE "Key" = '%s'
        """ % key
        row = next(self.query_iter(q))
        if row:
            return row[0]

    def clear_cache(self):
        self.cached_work_editions_ranges.clear()
        self.cache.clear()
        self.ia_cache.clear()


def simple_timeit(fn):
    start = time.time()
    result = fn()
    end = time.time()
    return end - start, result


async def simple_timeit_async(awaitable: Awaitable):
    start = time.time()
    result = await awaitable
    end = time.time()
    return end - start, result


def build_job_query(
        job: Literal['works', 'orphans', 'authors'],
        start_at: str = None,
        offset: int = 0,
        last_modified: str = None,
        limit: int = None
) -> str:
    """
    :param job: job to complete
    :param start_at: key (type-prefixed) to start from as opposed to offset; WAY more
    efficient since offset has to walk through all `offset` rows.
    :param offset: Use `start_at` if possible.
    :param last_modified: Only import docs modified after this date.
    """
    type = {
        "works": "work",
        "orphans": "edition",
        "authors": "author"
    }[job]

    q_select = """SELECT "Key", "JSON" FROM test"""
    q_where = """WHERE "Type" = '/type/%s'""" % type
    q_order = """ORDER BY "Key" """
    q_offset = ""
    q_limit = ""

    if offset:
        q_offset = """OFFSET %d""" % offset

    if limit:
        q_limit = """LIMIT %d""" % limit

    if last_modified:
        q_where += """ AND "LastModified" >= '%s'""" % last_modified
        q_order = ""
        q_limit = ""

    if start_at:
        q_where += """ AND "Key" >= '%s'""" % start_at

    if job == 'orphans':
        q_where += """ AND "JSON" -> 'works' -> 0 ->> 'key' IS NULL"""

    return ' '.join([q_select, q_where, q_order, q_offset, q_limit])


async def main(
        cmd: Literal['index', 'fetch-end'],
        job: Literal['works', 'orphans', 'authors'],
        postgres="postgres.ini",
        ol="http://ol/",
        ol_config="../../conf/openlibrary.yml",
        solr: str = None,
        skip_solr_id_check=True,
        start_at: str = None,
        offset=0,
        limit=1,
        last_modified: str = None,
        progress: str = None,
        log_file: str = None,
        log_level=logging.INFO,
        dry_run=False,
) -> None:
    """
    :param cmd: Whether to do the index or just fetch end of the chunk
    :param job: Type to index. Orphans gets orphaned editions.
    :param postgres: Path to postgres config file
    :param ol: Open Library endpoint
    :param ol_config: Path to Open Library config file
    :param solr: Overwrite solr base url from ol_config
    :param start_at: key (type-prefixed) to start from as opposed to offset; WAY more
    efficient since offset has to walk through all `offset` rows.
    :param offset: Use `start_at` if possible.
    :param last_modified: Limit results to those modifier >= this date
    :param progress: Where/if to save progress indicator to
    :param log_file: Redirect logs to file instead of stdout
    """

    logging.basicConfig(
        filename=log_file,
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )

    if solr:
        update_work.set_solr_base_url(solr)

    PLogEntry = namedtuple('PLogEntry', [
        'seen', 'total', 'percent', 'elapsed', 'q_1', 'q_auth', 'q_ia', 'cached',
        'ia_cache', 'next'])

    class PLog:
        def __init__(self, filename):
            """
            :param str or None filename:
            """
            self.filename = filename
            self.last_entry = None

        def log(self, entry):
            """
            :param PLogEntry entry:
            """
            self.last_entry = entry
            if self.filename:
                with open(progress, 'a') as f:
                    f.write('\t'.join(
                        self.fmt(k, val) for k, val in entry._asdict().items()))
                    f.write('\n')

        def update(self, seen=None, total=None, percent=None, elapsed=None, q_1=None,
                   q_auth=None, cached=None, q_ia=None, ia_cache=None, next=None):
            """
            :param str or int or None seen:
            :param str or int or None total:
            :param str or float or None percent:
            :param str or float or None elapsed:
            :param str or float or None q_1:
            :param str or float or None q_auth:
            :param str or int or None cached:
            :param str or float or None q_ia:
            :param str or int or None ia_cache:
            :param str or None next:
            :return: None
            """
            args = locals()
            entry = self.last_entry._replace(**{
                f: args[f] for f in PLogEntry._fields if args[f] is not None
            })
            self.log(entry)

        def fmt(self, k, val):
            """
            :param str k:
            :param Any val:
            :rtype: str
            """
            if val is None:
                return '?'
            if isinstance(val, str):
                return val
            if k == 'percent':
                return '%.2f%%' % (100 * val)
            if k in ['elapsed', 'q_1', 'q_auth', 'q_ia']:
                return '%.2fs' % val
            if isinstance(val, float):
                return '%.2f' % val
            if k == 'next':
                return val.split('/')[-1]
            return str(val)

    plog = PLog(progress)

    # load the contents of the config?
    with LocalPostgresDataProvider(postgres) as db:
        # Check to see where we should be starting from
        if cmd == 'fetch-end':
            next_start_query = build_job_query(job, start_at, limit, last_modified, 1)
            next_start_results = db.query_all(next_start_query)
            if next_start_results:
                print(next_start_results[0][0])
            return

        logger.info(json.dumps({
            'scope': 'solr_builder::main',
            'event': 'Indexing started',
            'start_at': start_at,
        }))
        load_configs(ol, ol_config, db)
        q = build_job_query(job, start_at, offset, last_modified, limit)

        if progress:
            # Clear the file
            with open(progress, 'w') as f:
                f.write('')
            with open(progress, 'a') as f:
                f.write('Calculating total... ')

        start = time.time()
        q_count = """SELECT COUNT(*) FROM(%s) AS foo""" % q
        count = db.query_all(q_count)[0][0]
        end = time.time()

        if progress:
            with open(progress, 'a') as f:
                f.write('%d (%.2fs)\n' % (count, end - start))
                f.write('\t'.join(PLogEntry._fields) + '\n')

        plog.log(
            PLogEntry(0, count, '0.00%', 0, '?', '?', '?', '?', '?', start_at or '?'))
        plog.update(q_1=0, q_auth=0, q_ia=0)

        start = time.time()
        seen = 0
        for batch in db.query_batched(q, size=1000, cache_json=True):
            keys = [x[0] for x in batch]
            plog.update(next=keys[0], cached=len(db.cache), ia_cache=0)

            with LocalPostgresDataProvider(postgres) as db2:
                key_range = [keys[0], keys[-1]]

                if job == "works":
                    # cache editions
                    editions_time, _ = simple_timeit(
                        lambda: db2.cache_work_editions(*key_range))
                    plog.update(q_1=plog.last_entry.q_1 + editions_time,
                                cached=len(db.cache) + len(db2.cache))

                    # cache editions' ocaid metadata
                    ocaids_time, _ = await simple_timeit_async(
                        db2.cache_cached_editions_ia_metadata())
                    plog.update(q_ia=plog.last_entry.q_ia + ocaids_time,
                                ia_cache=len(db2.ia_cache))

                    # cache authors
                    authors_time, _ = simple_timeit(
                        lambda: db2.cache_work_authors(*key_range))
                    plog.update(q_auth=plog.last_entry.q_auth + authors_time,
                                cached=len(db.cache) + len(db2.cache))
                elif job == "orphans":
                    # cache editions' ocaid metadata
                    ocaids_time, _ = await simple_timeit_async(
                        db2.cache_cached_editions_ia_metadata())
                    plog.update(q_ia=plog.last_entry.q_ia + ocaids_time,
                                ia_cache=len(db2.ia_cache))

                    # cache authors
                    authors_time, _ = simple_timeit(
                        lambda: db2.cache_edition_authors(*key_range))
                    plog.update(q_auth=plog.last_entry.q_auth + authors_time,
                                cached=len(db.cache) + len(db2.cache))
                elif job == "authors":
                    # Nothing to cache; update_work.py queries solr directly for each
                    # other, and provides no way to cache.
                    pass

                # Store in main cache
                db.cache.update(db2.cache)
                db.ia_cache.update(db2.ia_cache)
                db.cached_work_editions_ranges += db2.cached_work_editions_ranges

            update_keys(keys, commit=False, commit_way_later=True, solr8=True,
                        skip_id_check=skip_solr_id_check,
                        update='quiet' if dry_run else 'update')

            seen += len(keys)
            plog.update(
                elapsed=time.time() - start,
                seen=seen, percent=seen / count,
                cached=len(db.cache), ia_cache=len(db.ia_cache))

            db.clear_cache()

if __name__ == '__main__':
    from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI
    FnToCLI(main).run()
