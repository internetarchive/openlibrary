from __future__ import annotations

import json
import logging
import time
import uuid
from collections import namedtuple
from collections.abc import Awaitable, Iterator
from configparser import ConfigParser
from pathlib import Path
from typing import Any, Literal, Self

import aiofiles
import psycopg2

from openlibrary.core.bookshelves import Bookshelves
from openlibrary.core.ratings import Ratings, WorkRatingsSummary
from openlibrary.solr import update
from openlibrary.solr.data_provider import DataProvider, WorkReadingLogSolrSummary
from openlibrary.solr.update import load_configs, update_keys
from openlibrary.utils.open_syllabus_project import set_osp_dump_location

logger = logging.getLogger("openlibrary.solr-builder")


def config_section_to_dict(config_file: str, section: str) -> dict:
    """
    Read a config file's section as a dict

    :param str config_file: filename of config file
    :param str section: section to pull data from
    :return: dict of key value pairs
    """
    config = ConfigParser()
    config.read(config_file)
    result = {key: config.get(section, key) for key in config.options(section)}
    return result


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

    def __init__(self, db_conf_file: str):
        """
        :param str db_conf_file: file to DB config with [postgres] section
        """
        super().__init__()
        self._db_conf = config_section_to_dict(db_conf_file, "postgres")
        self._conn: psycopg2._psycopg.connection = None
        self.cache: dict = {}
        self.cached_work_editions_ranges: list = []
        self.cached_work_ratings: dict[str, WorkRatingsSummary] = {}
        self.cached_work_reading_logs: dict[str, WorkReadingLogSolrSummary] = {}

    def __enter__(self) -> Self:
        """
        :rtype: LocalPostgresDataProvider
        """
        self._conn = psycopg2.connect(**self._db_conf)
        return self

    def __exit__(self, type, value, traceback):
        self.clear_cache()
        self._conn.close()

    def query_all(self, query: str, json_cache: dict | None = None) -> list:
        """
        :param json_cache: if specified, adds records in the second column to the
        provided dict, with the first column as keys
        """
        cur = self._conn.cursor()
        cur.execute(query)
        rows = cur.fetchall()
        cur.close()

        if rows:
            if json_cache is not None:
                json_cache.update({row[0]: row[1] for row in rows})
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
            yield from rows

        cur.close()

    def query_batched(
        self,
        query: str,
        size: int,
        cursor_name: str | None = None,
        cache_json: bool = False,
    ) -> Iterator:
        """
        :param str query:
        :param int size:
        :param str or None cursor_name: if wanting to use a specific cursor
        :param bool cache_json: Requires the select statement to be "Key", "JSON"
        :return: None
        """
        # Not sure if this name needs to be unique
        cursor_name = (
            cursor_name or 'solr_builder_server_side_cursor_' + uuid.uuid4().hex
        )
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

    def cache_edition_works(self, lo_key, hi_key):
        q = f"""
            SELECT works."Key", works."JSON"
            FROM "test" editions
            INNER JOIN test works
                ON editions."JSON" -> 'works' -> 0 ->> 'key' = works."Key"
            WHERE editions."Type" = '/type/edition'
                AND '{lo_key}' <= editions."Key" AND editions."Key" <= '{hi_key}'
        """
        self.query_all(q, json_cache=self.cache)

    def cache_work_editions(self, lo_key, hi_key):
        q = f"""
            SELECT "Key", "JSON"
            FROM "test"
            WHERE "Type" = '/type/edition'
                AND '{lo_key}' <= "JSON" -> 'works' -> 0 ->> 'key'
                AND "JSON" -> 'works' -> 0 ->> 'key' <= '{hi_key}'
        """
        self.query_all(q, json_cache=self.cache)
        self.cached_work_editions_ranges.append((lo_key, hi_key))

    def cache_edition_authors(self, lo_key, hi_key):
        q = f"""
            SELECT authors."Key", authors."JSON"
            FROM "test" editions
            INNER JOIN test works
                ON editions."JSON" -> 'works' -> 0 ->> 'key' = works."Key"
            INNER JOIN test authors
                ON works."JSON" -> 'authors' -> 0 -> 'author' ->> 'key' = authors."Key"
            WHERE editions."Type" = '/type/edition'
                AND editions."JSON" -> 'works' -> 0 ->> 'key' IS NULL
                AND '{lo_key}' <= editions."Key" AND editions."Key" <= '{hi_key}'
        """
        self.query_all(q, json_cache=self.cache)

    def cache_work_authors(self, lo_key, hi_key):
        # Cache upto first five authors
        q = f"""
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
            AND '{lo_key}' <= works."Key" AND works."Key" <= '{hi_key}'
        """
        self.query_all(q, json_cache=self.cache)

    def cache_work_ratings(self, lo_key, hi_key):
        q = f"""
            SELECT "WorkKey", json_build_object(
                'ratings_count_1', count(*) filter (where "Rating" = 1),
                'ratings_count_2', count(*) filter (where "Rating" = 2),
                'ratings_count_3', count(*) filter (where "Rating" = 3),
                'ratings_count_4', count(*) filter (where "Rating" = 4),
                'ratings_count_5', count(*) filter (where "Rating" = 5)
            )
            FROM "ratings"
            WHERE '{lo_key}' <= "WorkKey" AND "WorkKey" <= '{hi_key}'
            GROUP BY "WorkKey"
            ORDER BY "WorkKey" asc
        """
        self.query_all(q, json_cache=self.cached_work_ratings)
        for row in self.cached_work_ratings.values():
            row.update(
                Ratings.work_ratings_summary_from_counts(
                    [row[f'ratings_count_{i}'] for i in range(1, 6)]
                )
            )

    def cache_work_reading_logs(self, lo_key: str, hi_key: str):
        per_shelf_fields = ', '.join(
            f"""
                '{json_name}_count', count(*) filter (where "Shelf" = '{human_name}')
            """.strip()
            for json_name, human_name in zip(
                Bookshelves.PRESET_BOOKSHELVES_JSON.keys(),
                Bookshelves.PRESET_BOOKSHELVES.keys(),
            )
        )
        q = f"""
            SELECT "WorkKey", json_build_object(
                'readinglog_count', count(*),
                {per_shelf_fields}
            )
            FROM "reading_log"
            WHERE '{lo_key}' <= "WorkKey" AND "WorkKey" <= '{hi_key}'
            GROUP BY "WorkKey"
            ORDER BY "WorkKey" asc
        """
        self.query_all(q, json_cache=self.cached_work_reading_logs)

    async def cache_cached_editions_ia_metadata(self):
        ocaids = list({doc['ocaid'] for doc in self.cache.values() if 'ocaid' in doc})
        await self.preload_metadata(ocaids)

    def find_redirects(self, key):
        """Returns keys of all things which redirect to this one."""
        logger.debug("find_redirects %s", key)
        q = (
            """
        SELECT "Key" FROM test
        WHERE "Type" = '/type/redirect' AND "JSON" ->> 'location' = '%s'
        """
            % key
        )
        return [r[0] for r in self.query_iter(q)]

    def get_editions_of_work_direct(self, work):
        q = (
            """
        SELECT "JSON" FROM test
        WHERE "Type" = '/type/edition' AND "JSON" -> 'works' -> 0 ->> 'key' = '%s'
        """
            % work['key']
        )
        return [r[0] for r in self.query_iter(q)]

    def get_editions_of_work(self, work):
        # They should all be cached...
        cache_hit = any(
            lo <= work['key'] <= hi for (lo, hi) in self.cached_work_editions_ranges
        )
        if cache_hit:
            return [
                doc
                for doc in self.cache.values()
                if (
                    doc['type']['key'] == '/type/edition'
                    and safeget(lambda: doc['works'][0]['key'] == work['key'])
                )
            ]
        else:
            return self.get_editions_of_work_direct(work)

    def get_work_ratings(self, work_key: str) -> WorkRatingsSummary | None:
        return self.cached_work_ratings.get(work_key)

    def get_work_reading_log(self, work_key: str) -> WorkReadingLogSolrSummary | None:
        return self.cached_work_reading_logs.get(work_key)

    async def get_document(self, key):
        if key in self.cache:
            logger.debug("get_document cache hit %s", key)
            return self.cache[key]

        logger.debug("get_document cache miss %s", key)

        q = (
            """
        SELECT "JSON" FROM test
        WHERE "Key" = '%s'
        """
            % key
        )
        row = next(self.query_iter(q))
        if row:
            return row[0]

    def clear_cache(self):
        super().clear_cache()
        self.cached_work_editions_ranges.clear()
        self.cached_work_ratings.clear()
        self.cache.clear()


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
    job: Literal['works', 'orphans', 'authors', 'lists'],
    start_at: str | None = None,
    offset: int = 0,
    last_modified: str | None = None,
    limit: int | None = None,
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
        "authors": "author",
        "lists": "list",
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

    return f"{q_select} {q_where} {q_order} {q_offset} {q_limit}"


async def main(
    cmd: Literal['index', 'fetch-end'],
    job: Literal['works', 'orphans', 'authors', 'lists'],
    osp_dump: Path | None = None,
    postgres="postgres.ini",
    ol="http://ol/",
    ol_config="../../conf/openlibrary.yml",
    solr: str | None = None,
    skip_solr_id_check: bool = True,
    start_at: str | None = None,
    offset=0,
    limit=1,
    last_modified: str | None = None,
    progress: str | None = None,
    log_file: str | None = None,
    log_level=logging.INFO,
    dry_run: bool = False,
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
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    if solr:
        update.set_solr_base_url(solr)

    set_osp_dump_location(osp_dump)

    PLogEntry = namedtuple(
        'PLogEntry',
        [
            'seen',
            'total',
            'percent',
            'elapsed',
            'q_1',
            'q_auth',
            'q_ia',
            'cached',
            'ia_cache',
            'next',
        ],
    )

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
                    f.write(
                        '\t'.join(
                            self.fmt(k, val) for k, val in entry._asdict().items()
                        )
                    )
                    f.write('\n')

        def update(
            self,
            seen: str | int | None = None,
            total: str | int | None = None,
            percent: str | float | None = None,
            elapsed: str | float | None = None,
            q_1: str | float | None = None,
            q_auth: str | float | None = None,
            cached: str | int | None = None,
            q_ia: str | float | None = None,
            ia_cache: str | int | None = None,
            next: str | None = None,
        ) -> None:
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
            entry = self.last_entry._replace(
                **{f: args[f] for f in PLogEntry._fields if args[f] is not None}
            )
            self.log(entry)

        def fmt(self, k: str, val: Any) -> str:
            """
            :param str k:
            :param Any val:
            :return: str
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

        logger.info(
            json.dumps(
                {
                    'scope': 'solr_builder::main',
                    'event': 'Indexing started',
                    'start_at': start_at,
                }
            )
        )
        load_configs(ol, ol_config, db)
        q = build_job_query(job, start_at, offset, last_modified, limit)

        if progress:
            # Clear the file
            async with aiofiles.open(progress, 'w') as f:
                await f.write('')
            async with aiofiles.open(progress, 'a') as f:
                await f.write('Calculating total... ')

        start = time.time()
        q_count = """SELECT COUNT(*) FROM(%s) AS foo""" % q
        count = db.query_all(q_count)[0][0]
        end = time.time()

        if progress:
            async with aiofiles.open(progress, 'a') as f:
                await f.write('%d (%.2fs)\n' % (count, end - start))
                await f.write('\t'.join(PLogEntry._fields) + '\n')

        plog.log(
            PLogEntry(0, count, '0.00%', 0, '?', '?', '?', '?', '?', start_at or '?')
        )
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
                        lambda: db2.cache_work_editions(*key_range)
                    )
                    plog.update(
                        q_1=plog.last_entry.q_1 + editions_time,
                        cached=len(db.cache) + len(db2.cache),
                    )

                    # cache editions' ocaid metadata
                    ocaids_time, _ = await simple_timeit_async(
                        db2.cache_cached_editions_ia_metadata()
                    )
                    plog.update(
                        q_ia=plog.last_entry.q_ia + ocaids_time,
                        ia_cache=len(db2.ia_cache),
                    )

                    # cache authors
                    authors_time, _ = simple_timeit(
                        lambda: db2.cache_work_authors(*key_range)
                    )
                    plog.update(
                        q_auth=plog.last_entry.q_auth + authors_time,
                        cached=len(db.cache) + len(db2.cache),
                    )

                    # cache ratings and reading logs
                    db2.cache_work_ratings(*key_range)
                    db2.cache_work_reading_logs(*key_range)
                elif job == "orphans":
                    # cache editions' ocaid metadata
                    ocaids_time, _ = await simple_timeit_async(
                        db2.cache_cached_editions_ia_metadata()
                    )
                    plog.update(
                        q_ia=plog.last_entry.q_ia + ocaids_time,
                        ia_cache=len(db2.ia_cache),
                    )

                    # cache authors
                    authors_time, _ = simple_timeit(
                        lambda: db2.cache_edition_authors(*key_range)
                    )
                    plog.update(
                        q_auth=plog.last_entry.q_auth + authors_time,
                        cached=len(db.cache) + len(db2.cache),
                    )
                elif job == 'lists':
                    # Nothing to cache ; just need the lists themselves and
                    # they are already cached
                    pass
                elif job == "authors":
                    # Nothing to cache; update.py queries solr directly for each
                    # other, and provides no way to cache.
                    pass

                # Store in main cache
                db.cache.update(db2.cache)
                db.ia_cache.update(db2.ia_cache)
                db.cached_work_editions_ranges += db2.cached_work_editions_ranges
                db.cached_work_ratings.update(db2.cached_work_ratings)
                db.cached_work_reading_logs.update(db2.cached_work_reading_logs)

            await update_keys(
                keys,
                commit=False,
                skip_id_check=skip_solr_id_check,
                update='quiet' if dry_run else 'update',
            )

            seen += len(keys)
            plog.update(
                elapsed=time.time() - start,
                seen=seen,
                percent=seen / count,
                cached=len(db.cache),
                ia_cache=len(db.ia_cache),
            )

            db.clear_cache()


if __name__ == '__main__':
    from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI

    FnToCLI(main).run()
