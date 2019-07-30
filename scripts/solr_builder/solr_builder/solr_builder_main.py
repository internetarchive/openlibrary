from __future__ import division

import ConfigParser
import logging
import time
import urllib
import urllib2
import uuid
from collections import namedtuple

import psycopg2
import simplejson

from openlibrary.core import ia
from openlibrary.solr.data_provider import DataProvider
from openlibrary.solr.update_work import load_configs, update_keys, using_cython

logger = logging.getLogger("openlibrary.solr-builder")


def config_section_to_dict(config_file, section):
    """
    Read a config file's section as a dict

    :param str config_file: filename of config file
    :param str section: section to pull data from
    :return: dict of key value pairs
    :rtype: dict
    """
    config = ConfigParser.ConfigParser()
    config.read(config_file)
    result = { key: config.get(section, key) for key in config.options(section) }
    return result


def batches(itrble, size):
    """
    :param collections.Sized itrble:
    :param int size:
    :rtype: typings.Generator[list, None, None]
    """
    start = 0
    end = 0
    while end < len(itrble):
        end = start + size
        yield itrble[start:end]
        start = end


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
        self.ia_cache = dict()
        self.ia = None

    def __enter__(self):
        """
        :rtype: LocalPostgresDataProvider
        """
        self._conn = psycopg2.connect(**self._db_conf)
        return self

    def __exit__(self, type, value, traceback):
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
        cursor_name = cursor_name or 'solr_builder_server_side_cursor_' + uuid.uuid4().hex
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
    def _get_lite_metadata(ocaids, rows=1000):
        url = ''.join(["https://archive.org/advancedsearch.php?",
                       "q=identifier:(" + urllib.quote(' OR '.join(ocaids)) + ")",
                       "&fl[]=identifier&fl[]=boxid&fl[]=collection",
                       "&rows=%d&page=1&output=json&save=yes" % rows])
        resp_str = urllib2.urlopen(url).read()
        return simplejson.loads(resp_str)['response']

    def cache_ia_metadata(self, ocaids, batch_size=750):
        """
        :param list of str ocaids:
        :param int batch_size:
        :return: None
        """
        for b in batches(ocaids, batch_size):
            try:
                for doc in self._get_lite_metadata(b, rows=batch_size)['docs']:
                    self.ia_cache[doc['identifier']] = doc
            except:
                logger.error("Error while caching IA", exc_info=True)

    def cache_edition_works(self, lo_key, hi_key):
        q = """
            SELECT works."Key", works."JSON"
            FROM "test" editions
            INNER JOIN test works ON editions."JSON" -> 'works' -> 0 ->> 'key' = works."Key"
            WHERE editions."Type" = '/type/edition' AND editions."Key" BETWEEN '%s' AND '%s'
        """ % (lo_key, hi_key)
        self.query_all(q, cache_json=True)

    def cache_work_editions(self, lo_key, hi_key):
        q = """
            SELECT "Key", "JSON"
            FROM "test"
            WHERE "Type" = '/type/edition' AND "JSON" -> 'works' -> 0 ->> 'key' BETWEEN '%s' AND '%s'
        """ % (lo_key, hi_key)
        self.query_all(q, cache_json=True)

    def cache_edition_authors(self, lo_key, hi_key):
        q = """
            SELECT authors."Key", authors."JSON"
            FROM "test" editions
            INNER JOIN test works ON editions."JSON" -> 'works' -> 0 ->> 'key' = works."Key"
            INNER JOIN test authors ON works."JSON" -> 'authors' -> 0 -> 'author' ->> 'key' = authors."Key"
            WHERE editions."Type" = '/type/edition' AND editions."Key" BETWEEN '%s' AND '%s'
        """ % (lo_key, hi_key)
        self.query_all(q, cache_json=True)

    def cache_work_authors(self, lo_key, hi_key):
        q = """
            SELECT authors."Key", authors."JSON"
            FROM "test" works
            INNER JOIN "test" authors ON works."JSON" -> 'authors' -> 0 -> 'author' ->> 'key' = authors."Key"
            WHERE works."Type" = '/type/work' AND works."Key" BETWEEN '%s' AND '%s'
        """ % (lo_key, hi_key)
        self.query_all(q, cache_json=True)

    def cache_cached_editions_ia_metadata(self):
        # Limit length of OCAIDs to avoid really long URLs. They just won't be cached.
        ocaids = [doc['ocaid'] for doc in self.cache.itervalues() if 'ocaid' in doc and len(doc['ocaid']) < 50]
        self.cache_ia_metadata(ocaids)

    def find_redirects(self, key):
        """Returns keys of all things which redirect to this one."""
        logger.info("find_redirects %s", key)
        q = """
        SELECT "Key" FROM test
        WHERE "Type" = '/type/redirect' AND "JSON" ->> 'location' = '%s'
        """ % key
        return [r[0] for r in self.query_iter(q)]

    def get_editions_of_work(self, work):
        logger.info("find_editions_of_work %s", work['key'])
        q = """
        SELECT "JSON" FROM test
        WHERE "Type" = '/type/edition' AND "JSON" -> 'works' -> 0 ->> 'key' = '%s'
        """ % work['key']
        return [r[0] for r in self.query_iter(q)]

    def get_metadata(self, identifier):
        logger.info("find_metadata %s", identifier)

        if identifier in self.ia_cache:
            return self.ia_cache[identifier]

        return ia.get_metadata(identifier)

    def get_document(self, key):
        logger.info("get_document %s", key)

        if key in self.cache:
            return self.cache[key]

        q = """
        SELECT "JSON" FROM test
        WHERE "Key" = '%s'
        """ % key
        row = self.query_iter(q).next()
        if row:
            return row[0]

    def clear_cache(self):
        self.cache = dict()
        self.ia_cache = dict()
        pass


def simple_timeit(fn):
    start = time.time()
    result = fn()
    end = time.time()
    return end - start, result


def build_job_query(job, start_at, offset, last_modified, limit):
    """

    :param str job: job to complete. One of 'works', 'orphans', 'authors'
    :param str or None start_at: key (type-prefixed) to start from as opposed to offset; WAY more efficient since offset
     has to walk through all `offset` rows.
    :param int offset: Use `start_at` if possible.
    :param str or None last_modified: Only import docs modified after this date.
    :param int or None limit:
    :rtype: str
    """
    type = {
        "works": "work",
        "orphans": "edition",
        "authors": "author"
    }[job]

    q_select = """SELECT "Key", "JSON" FROM test"""
    q_where = """WHERE "Type" = '/type/%s'""" % type
    q_order = """ORDER BY "Key" """
    q_offset = """OFFSET %d""" % offset
    q_limit = ""

    if limit:
        q_limit = """LIMIT %d""" % limit

    if last_modified:
        q_where += """ AND "LastModified" >= '%s'""" % last_modified
        q_order = ""
        q_offset = ""
        q_limit = ""

    if start_at:
        q_where += """ AND "Key" >= '%s'""" % start_at
        q_offset = ""

    if job == 'orphans':
        q_where += """ AND "JSON" -> 'works' -> 0 ->> 'key' IS NULL"""
        q_order = ""
        q_offset = ""
        q_limit = ""

    return ' '.join([q_select, q_where, q_order, q_offset, q_limit])


def main(job, postgres="postgres.ini", ol="http://ol/", ol_config="../../conf/openlibrary.yml",
         start_at=None, offset=0, limit=1, last_modified=None,
         progress=None, log_file=None, log_level=logging.WARN
         ):
    """
    :param str job: job to complete. One of 'works', 'orphans', 'authors'
    :param str postgres: path to postgres config file
    :param str ol: openlibrary endpoint
    :param str ol_config: path to openlibrary config file
    :param str or None start_at: key (type-prefixed) to start from as opposed to offset; WAY more efficient since offset
     has to walk through all `offset` rows.
    :param int offset: Use `start_at` if possible.
    :param int limit:
    :param str or None last_modified: Limit results to those modifier >= this date
    :param str or None progress: Where/if to save progress indicator to
    :param str or None log_file: Redirect logs to file instead of stdout
    :param int log_level:
    :return: None
    """

    # Create the log/progress files now, so that they're accessible
    for path in [log_file, progress]:
        if path:
            open(path, 'a').close()

    logging.basicConfig(
        filename=log_file,
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )

    PLogEntry = namedtuple('PLogEntry', [
        'seen', 'total', 'percent', 'elapsed', 'q_1', 'q_auth', 'q_ia', 'cached', 'ia_cache', 'next'])

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
                    f.write('\t'.join(self.fmt(k, val) for k, val in entry._asdict().iteritems()))
                    f.write('\n')

        def update(self, seen=None, total=None, percent=None, elapsed=None, q_1=None, q_auth=None,
                   cached=None, q_ia=None, ia_cache=None, next=None):
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
                return '%.2f%%' % (100*val)
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
        load_configs(ol, ol_config, db)

        q = build_job_query(job, start_at, offset, last_modified, limit)

        count = None
        if progress:
            with open(progress, 'w', buffering=0) as f:
                f.write('Calculating total... ')
                q_count = """SELECT COUNT(*) FROM(%s) AS foo""" % q
                start = time.time()
                count = db.query_all(q_count)[0][0]
                end = time.time()
                f.write('%d (%.2fs)\n' % (count, end - start))
                f.write('\t'.join(PLogEntry._fields) + '\n')

        plog.log(PLogEntry(0, count, '0.00%', 0, '?', '?', '?', '?', '?', start_at or '?'))

        start = time.time()
        seen = 0
        for batch in db.query_batched(q, size=5000, cache_json=True):
            keys = [x[0] for x in batch]
            plog.update(next=keys[0], cached=len(db.cache), ia_cache=0, q_1='?', q_auth='?', q_ia='?')

            with LocalPostgresDataProvider(postgres) as db2:
                key_range = [keys[0], keys[-1]]

                if job == "works":
                    # cache editions
                    editions_time, _ = simple_timeit(lambda: db2.cache_work_editions(*key_range))
                    plog.update(q_1=editions_time, cached=len(db.cache) + len(db2.cache))

                    # cache editions' ocaid metadata
                    ocaids_time, _ = simple_timeit(lambda: db2.cache_cached_editions_ia_metadata())
                    plog.update(q_ia=ocaids_time, ia_cache=len(db2.ia_cache))

                    # cache authors
                    authors_time, _ = simple_timeit(lambda: db2.cache_work_authors(*key_range))
                    plog.update(q_auth=authors_time, cached=len(db.cache) + len(db2.cache))
                elif job == "orphans":
                    # cache editions' ocaid metadata
                    ocaids_time, _ = simple_timeit(lambda: db2.cache_cached_editions_ia_metadata())
                    plog.update(q_ia=ocaids_time, ia_cache=len(db2.ia_cache))

                    # cache authors
                    authors_time, _ = simple_timeit(lambda: db2.cache_work_authors(*key_range))
                    plog.update(q_auth=authors_time, cached=len(db.cache) + len(db2.cache))
                elif job == "authors":
                    # Nothing to cache; update_work.py queries solr directly for each other, and provides no way to
                    # cache.
                    pass

                # Store in main cache
                db.cache.update(db2.cache)
                db.ia_cache.update(db2.ia_cache)

            update_keys(keys, commit=False, commit_way_later=True)

            seen += len(keys)
            plog.update(
                elapsed=time.time() - start,
                seen=seen, percent=seen/count,
                cached=len(db.cache), ia_cache=len(db.ia_cache))

            db.clear_cache()
