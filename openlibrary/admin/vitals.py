import yaml
from statsd import StatsClient

from openlibrary.core import db

STATSD_EVENT_PREFIX = "stats.ol.participation"

def write_to_statsd(configfile, stats):
    def configure_statsd(_configfile):
        with open(_configfile) as f:
            configs = yaml.safe_load(f)
        url = configs.get("admin", {}).get("statsd_server", None)
        if not url:
            raise KeyError("StatsD server not configured")
        split_url = url.split(":")
        return StatsClient(split_url[0], split_url[1])

    statsd = configure_statsd(configfile)

    # Star ratings
    statsd.gauge(
        f"{STATSD_EVENT_PREFIX}.star_ratings.hourly.total",
        stats.get("star_ratings")
    )
    statsd.gauge(
        f"{STATSD_EVENT_PREFIX}.star_ratings.distinct.hourly.total",
        stats.get("distinct_star_ratings")
    )

    # List creation
    statsd.gauge(
        f"{STATSD_EVENT_PREFIX}.lists.hourly.total",
        stats.get("list_counts")
    )
    statsd.gauge(
        f"{STATSD_EVENT_PREFIX}.lists.distinct.hourly.total",
        stats.get("distinct_list_counts")
    )

    # Reading log counts
    statsd.gauge(
        f"{STATSD_EVENT_PREFIX}.reading_logs.want_to_read.hourly.total",
        stats.get("reading_logs", {}).get("want_to_read")
    )
    statsd.gauge(
        f"{STATSD_EVENT_PREFIX}.reading_logs.currently_reading.hourly.total",
        stats.get("reading_logs", {}).get("currently_reading")
    )
    statsd.gauge(
        f"{STATSD_EVENT_PREFIX}.reading_logs.already_read.hourly.total",
        stats.get("reading_logs", {}).get("already_read")
    )
    statsd.gauge(
        f"{STATSD_EVENT_PREFIX}.reading_logs.stopped_reading.hourly.total",
        stats.get("reading_logs", {}).get("stopped_reading")
    )
    statsd.gauge(
        f"{STATSD_EVENT_PREFIX}.reading_logs.want_to_read.distinct.hourly.total",
        stats.get("distinct_reading_logs", {}).get("want_to_read")
    )
    statsd.gauge(
        f"{STATSD_EVENT_PREFIX}.reading_logs.currently_reading.distinct.hourly.total",
        stats.get("distinct_reading_logs", {}).get("currently_reading")
    )
    statsd.gauge(
        f"{STATSD_EVENT_PREFIX}.reading_logs.already_read.distinct.hourly.total",
             stats.get("distinct_reading_logs", {}).get("already_read")
    )
    statsd.gauge(
        f"{STATSD_EVENT_PREFIX}.reading_logs.stopped_reading.distinct.hourly.total",
        stats.get("distinct_reading_logs", {}).get("stopped_reading")
    )

def gather_participation_scores() -> dict[str, int | dict[str, int]]:
    results = {}
    results.update(calc_star_rating_counts())
    results.update(calc_reading_log_counts())
    results.update(calc_list_counts())
    return results

def calc_star_rating_counts() -> dict[str, int]:
    results = {}
    oldb = db.get_db()
    total_ratings_query = """
        select count(*) from ratings
        WHERE created >= date_trunc('hour', now() - interval '1 hour')
            AND created <  date_trunc('hour', now());
    """
    totals = oldb.query(total_ratings_query)
    results['star_ratings'] = next(iter(totals))['count']

    distinct_raters_query = """
        select count(distinct username) from ratings
        WHERE created >= date_trunc('hour', now() - interval '1 hour')
            AND created <  date_trunc('hour', now());
    """
    distinct_totals = oldb.query(distinct_raters_query)
    results["distinct_star_ratings"] = next(iter(distinct_totals))['count']

    return results

def calc_reading_log_counts() -> dict[str, dict[str, int]]:
    def normalize_shelf_name(shelf_name: str) -> str:
        return shelf_name.lower().replace(" ", "_")

    results = {}
    oldb = db.get_db()
    total_books_logged_query = """
        select count(bb.bookshelf_id) as cnt,
               b.name as bookshelf_name
        from bookshelves b
        left join bookshelves_books bb
            on bb.bookshelf_id = b.id
            and bb.created >= date_trunc('hour', now() - interval '1 hour')
            and bb.created <  date_trunc('hour', now())
        group by b.id, b.name
        order by b.id;
    """
    totals = oldb.query(total_books_logged_query)
    results['reading_logs'] = {
        normalize_shelf_name(i.bookshelf_name): i.cnt for i in totals
    }

    distinct_readers_logging_query = """
        select count(distinct bb.username) as cnt,
           b.name as bookshelf_name
        from bookshelves b
        left join bookshelves_books bb
            on bb.bookshelf_id = b.id
            and bb.created >= date_trunc('hour', now() - interval '1 hour')
            and bb.created <  date_trunc('hour', now())
        group by b.id, b.name
        order by b.id;
    """
    distinct_totals = oldb.query(distinct_readers_logging_query)
    results["distinct_reading_logs"] = {
        normalize_shelf_name(i.bookshelf_name): i.cnt for i in distinct_totals
    }

    return results

def calc_list_counts() -> dict[str, int]:
    results = {}
    oldb = db.get_db()
    total_lists_query = """
        select count(*) from thing where type = (select id from thing where key = '/type/list')
            AND created >= date_trunc('hour', now() - interval '1 hour')
            AND created <  date_trunc('hour', now());
    """
    totals = oldb.query(total_lists_query)
    results["list_counts"] = next(iter(totals))['count']

    distinct_creators_query = """
        SELECT COUNT(DISTINCT split_part(key, '/', 3)) AS distinct_list_creators
        FROM thing
        WHERE type = (SELECT id FROM thing WHERE key = '/type/list')
            AND created >= date_trunc('hour', now() - interval '1 hour')
            AND created <  date_trunc('hour', now());
    """
    distinct_totals = oldb.query(distinct_creators_query)
    results["distinct_list_counts"] = next(iter(distinct_totals))['distinct_list_creators']

    return results

def calc_edit_counts() -> dict[str, str]:
    raise NotImplementedError()
