"""Hooks for collecting performance stats.
"""
from __future__ import print_function

import logging
import time
import traceback

from infogami.utils.app import find_page, find_view, find_mode
from openlibrary.core import stats as graphite_stats
import web
from infogami import config
from infogami.utils import (
    delegate,
    stats,
)

import openlibrary.plugins.openlibrary.filters as stats_filters

l = logging.getLogger("openlibrary.stats")
TIME_BUCKETS = [10, 100, 1000, 5000, 10000, 20000]  # in ms

filters = {}

def evaluate_and_store_stat(name, stat, summary):
    """Evaluates whether the given statistic is to be recorded and if
    so, records it."""
    global filters
    if not summary:
        return
    try:
        f = filters[stat.filter]
    except KeyError:
        l.warning("Filter %s not registered", stat.filter)
        return
    try:
        if f(**stat):
            if "time" in stat:
                graphite_stats.put(name, summary[stat.time]["time"] * 100)
            elif "count" in stat:
                #print "Storing count for key %s"%stat.count
                # XXX-Anand: where is the code to update counts?
                pass
            else:
                l.warning("No storage item specified for stat %s", name)
    except Exception as k:
        l.warning("Error while storing stats (%s). Complete traceback follows"%k)
        l.warning(traceback.format_exc())

def update_all_stats(stats_summary):
    """
    Run through the filters and record requested items in graphite
    """
    for stat in config.get("stats", []):
        evaluate_and_store_stat(stat, config.stats.get(stat), stats_summary)

def stats_hook():
    """web.py unload hook to add X-OL-Stats header.

    This info can be written to lighttpd access log for collecting

    Also, send stats to graphite using statsd
    """
    stats_summary = stats.stats_summary()
    update_all_stats(stats_summary)
    try:
        if "stats-header" in web.ctx.features:
            web.header("X-OL-Stats", format_stats(stats_summary))
    except Exception as e:
        # don't let errors in stats collection break the app.
        print(str(e), file=web.debug)

    # This name is misleading. It gets incremented for more than just pages.
    # E.g. *.json requests (even ajax), image requests. Although I can't
    # see any *.js requests? So not sure exactly when we're called here.
    # FURTHERMORE: pages that get e.g. 500 status codes don't get here
    # either; that needs to be in an internalerrors hook
    graphite_stats.increment('ol.pageviews')

    memcache_hits = 0
    memcache_misses = 0
    for s in web.ctx.get("stats", []):
        if s.name == 'memcache.get':
            if s.data['hit']:
                memcache_hits += 1
            else:
                memcache_misses += 1

    if memcache_hits:
        graphite_stats.increment('ol.memcache.hits', memcache_hits)
    if memcache_misses:
        graphite_stats.increment('ol.memcache.misses', memcache_misses)

    for name, value in stats_summary.items():
        name = name.replace(".", "_")
        time = value.get("time", 0.0) * 1000
        key  = 'ol.'+name
        graphite_stats.put(key, time)

def format_stats(stats):
    s = " ".join("%s %d %0.03f" % entry for entry in process_stats(stats))
    return '"%s"' %s

labels = {
    "total": "TT",
    "memcache": "MC",
    "infobase": "IB",
    "solr": "SR",
    "archive.org": "IA",
    "couchdb": "CD",
}

def process_stats(stats):
    """Process stats and returns a list of (label, count, time) for each entry.

    Entries like "memcache.get" and "memcache.set" will be collapsed into "memcache".
    """
    d = {}
    for name, value in stats.items():
        name = name.split(".")[0]

        label = labels.get(name, "OT")
        count = value.get("count", 0)
        time = value.get("time", 0.0)

        xcount, xtime = d.get(label, [0, 0])
        d[label] = xcount + count, xtime + time

    return [(label, count, time) for label, (count, time) in sorted(d.items())]

def register_filter(name, function):
    global filters
    filters[name] = function


def _encode_key_part(key_part):
    """
    :param basestring key_part:
    """
    return key_part.replace('.', '_')


def _get_path_page_name(path):
    """
    :param str path: url path from e.g. web.ctx.path
    :rtype: str
    """

    pageClass, _ = find_page()
    if pageClass is None:  # Check for view handlers
        pageClass, _ = find_view()
    if pageClass is None:  # Check for mode handlers
        pageClass, _ = find_mode()

    result = pageClass.__name__
    if hasattr(pageClass, 'encoding'):
        result += '_' + pageClass.encoding

    return result


class GraphiteRequestStats:
    def __init__(self):
        self.start = None  # type: float
        self.end = None  # type: float
        self.state = None  # oneof 'started', 'completed'
        self.method = 'unknown'
        self.path_page_name = 'unknown'
        self.path_level_one = 'unknown'
        self.response_code = 'unknown'
        self.time_bucket = 'unknown'
        self.user = 'not_logged_in'
        self.duration = None

    def request_loaded(self):
        self.start = time.time()
        self.state = 'started'
        self._compute_fields()

    def request_unloaded(self):
        self.end = time.time()
        self.state = 'completed'
        self._compute_fields()

    def _compute_fields(self):
        if hasattr(web.ctx, 'method') and web.ctx.method:
            self.method = web.ctx.method

        if hasattr(web.ctx, 'path') and web.ctx.path:
            self.path_page_name = _get_path_page_name(web.ctx.path)
            path_parts = web.ctx.path.strip('/').split('/')
            self.path_level_one = path_parts[0].replace('.', '_') or 'home'

        if hasattr(web.ctx, 'status'):
            self.response_code = web.ctx.status.split(' ')[0]

        if self.end is not None:
            self.duration = (self.end - self.start) * 1000
            self.time_bucket = 'LONG'
            for upper in TIME_BUCKETS:
                if self.duration < upper:
                    self.time_bucket = '%dms' % upper
                    break

        if stats_filters.loggedin():
            self.user = 'logged_in'

    def to_metric(self):
        return '.'.join([
            'ol',
            'requests',
            self.state,
            self.method,
            self.response_code,
            self.user,
            self.path_level_one,
            self.path_page_name,
            self.time_bucket,
            'count',
        ])


def page_load_hook():
    web.ctx.graphiteRequestStats = GraphiteRequestStats()
    web.ctx.graphiteRequestStats.request_loaded()
    graphite_stats.increment(web.ctx.graphiteRequestStats.to_metric())


def page_unload_hook():
    web.ctx.graphiteRequestStats.request_unloaded()
    graphite_stats.increment(web.ctx.graphiteRequestStats.to_metric())


def setup():
    """
    This function is called from the main application startup
    routine to set things up.
    """

    # Initialise the stats filters
    register_filter("all", stats_filters.all)
    register_filter("url", stats_filters.url)
    register_filter("loggedin", stats_filters.loggedin)
    register_filter("not_loggedin", stats_filters.not_loggedin)

    delegate.app.add_processor(web.loadhook(page_load_hook))
    delegate.app.add_processor(web.unloadhook(page_unload_hook))
