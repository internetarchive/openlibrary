import yaml
from statsd import StatsClient

from openlibrary.core import db
from openlibrary.core.bookshelves import Bookshelves
from openlibrary.core.ratings import Ratings

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
    statsd.gauge(f"{STATSD_EVENT_PREFIX}.star_ratings.hourly.total", stats.get("star_ratings"))
    statsd.gauge(f"{STATSD_EVENT_PREFIX}.star_ratings.distinct.hourly.total", stats.get("distinct_star_ratings"))

    # List creation
    statsd.gauge(f"{STATSD_EVENT_PREFIX}.lists.hourly.total", stats.get("list_counts"))
    statsd.gauge(f"{STATSD_EVENT_PREFIX}.lists.distinct.hourly.total", stats.get("distinct_list_counts"))

    # Reading log counts
    statsd.gauge(f"{STATSD_EVENT_PREFIX}.reading_logs.want_to_read.hourly.total", stats.get("reading_logs", {}).get("want_to_read"))
    statsd.gauge(f"{STATSD_EVENT_PREFIX}.reading_logs.currently_reading.hourly.total", stats.get("reading_logs", {}).get("currently_reading"))
    statsd.gauge(f"{STATSD_EVENT_PREFIX}.reading_logs.already_read.hourly.total", stats.get("reading_logs", {}).get("already_read"))
    statsd.gauge(f"{STATSD_EVENT_PREFIX}.reading_logs.stopped_reading.hourly.total", stats.get("reading_logs", {}).get("stopped_reading"))
    statsd.gauge(f"{STATSD_EVENT_PREFIX}.reading_logs.want_to_read.distinct.hourly.total", stats.get("distinct_reading_logs", {}).get("want_to_read"))
    statsd.gauge(f"{STATSD_EVENT_PREFIX}.reading_logs.currently_reading.distinct.hourly.total", stats.get("distinct_reading_logs", {}).get("currently_reading"))
    statsd.gauge(f"{STATSD_EVENT_PREFIX}.reading_logs.already_read.distinct.hourly.total", stats.get("distinct_reading_logs", {}).get("already_read"))
    statsd.gauge(f"{STATSD_EVENT_PREFIX}.reading_logs.stopped_reading.distinct.hourly.total", stats.get("distinct_reading_logs", {}).get("stopped_reading"))


def gather_participation_scores() -> dict[str, int | dict[str, int]]:
    results: dict[str, int | dict[str, int]] = {}
    results.update(Ratings.calc_star_rating_counts())
    results.update(Bookshelves.calc_reading_log_counts())
    results.update(calc_list_counts())
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
    results["list_counts"] = next(iter(totals))["count"]

    distinct_creators_query = """
        SELECT COUNT(DISTINCT split_part(key, '/', 3)) AS distinct_list_creators
        FROM thing
        WHERE type = (SELECT id FROM thing WHERE key = '/type/list')
            AND created >= date_trunc('hour', now() - interval '1 hour')
            AND created <  date_trunc('hour', now());
    """
    distinct_totals = oldb.query(distinct_creators_query)
    results["distinct_list_counts"] = next(iter(distinct_totals))["distinct_list_creators"]

    return results
