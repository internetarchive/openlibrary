"""Hooks for collecting performance stats.
"""

import logging
import os
import re
import sys
import time
import traceback
from typing import Any, Optional

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

filters: dict[str, Any] = {}


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
                # print "Storing count for key %s"%stat.count
                # XXX-Anand: where is the code to update counts?
                pass
            else:
                l.warning("No storage item specified for stat %s", name)
    except Exception as k:
        l.warning("Error while storing stats (%s). Complete traceback follows" % k)
        l.warning(traceback.format_exc())


def update_all_stats(stats_summary):
    """
    Run through the filters and record requested items in graphite
    """
    for stat in config.get("stats", []):
        evaluate_and_store_stat(stat, config.stats.get(stat), stats_summary)


def stats_hook():
    """web.py unload hook to add X-OL-Stats header.

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
        graphite_stats.increment('ol.memcache.hits', memcache_hits, rate=0.025)
    if memcache_misses:
        graphite_stats.increment('ol.memcache.misses', memcache_misses, rate=0.025)

    for name, value in stats_summary.items():
        name = name.replace(".", "_")
        time = value.get("time", 0.0) * 1000
        key = 'ol.' + name
        graphite_stats.put(key, time)


def format_stats(stats):
    s = " ".join("%s %d %0.03f" % entry for entry in process_stats(stats))
    return '"%s"' % s


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
    if hasattr(pageClass, 'encoding') and not result.endswith(pageClass.encoding):
        result += '_' + pageClass.encoding

    return result


def _get_top_level_path_for_metric(full_path):
    """
    Normalize + shorten the string since it could be user-entered
    :param basestring full_path:
    :rtype: str
    """
    path_parts = full_path.strip('/').split('/')
    path = path_parts[0] or 'home'
    return path.replace('.', '_')[:50]


class GraphiteRequestStats:
    def __init__(self):
        self.start: Optional[float] = None
        self.end: Optional[float] = None
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
            # This can be entered by a user to be anything! We record 404s.
            self.path_level_one = _get_top_level_path_for_metric(web.ctx.path)

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
        return '.'.join(
            [
                'ol',
                'requests',
                self.state,
                self.method,
                self.response_code,
                self.user,
                self.path_level_one,
                'class_' + self.path_page_name,
                self.time_bucket,
                'count',
            ]
        )


def page_load_hook():
    web.ctx.graphiteRequestStats = GraphiteRequestStats()
    web.ctx.graphiteRequestStats.request_loaded()
    graphite_stats.increment(web.ctx.graphiteRequestStats.to_metric())


def page_unload_hook():
    web.ctx.graphiteRequestStats.request_unloaded()
    graphite_stats.increment(web.ctx.graphiteRequestStats.to_metric())


def increment_error_count(key):
    """
    :param str key: e.g. ol.exceptions or el.internal-errors-segmented
    """
    top_url_path = 'none'
    page_class = 'none'
    if web.ctx and hasattr(web.ctx, 'path') and web.ctx.path:
        top_url_path = _get_top_level_path_for_metric(web.ctx.path)
        page_class = _get_path_page_name(web.ctx.path)

    exception_type, exception_value, tback = sys.exc_info()
    exception_type_name = exception_type.__name__
    # Log exception file
    path = find_topmost_useful_file(exception_value, tback)
    path = os.path.split(path)

    # log just filename, unless it's code.py (cause that's useless!)
    ol_file = path[1]
    if path[1] in ('code.py', 'index.html', 'edit.html', 'view.html'):
        ol_file = os.path.split(path[0])[1] + '_' + _encode_key_part(path[1])

    metric_parts = [
        top_url_path,
        'class_' + page_class,
        ol_file,
        exception_type_name,
        'count',
    ]
    metric = '.'.join([_encode_key_part(p) for p in metric_parts])
    graphite_stats.increment(key + '.' + metric)


TEMPLATE_SYNTAX_ERROR_RE = re.compile(r"File '([^']+?)'")


def find_topmost_useful_file(exception, tback):
    """
    Find the topmost path in the traceback stack that's useful to report.

    :param BaseException exception: error from e.g. sys.exc_inf()
    :param TracebackType tback: traceback from e.g. sys.exc_inf()
    :rtype: basestring
    :return: full path
    """
    file_path = 'none'
    while tback is not None:
        cur_file = tback.tb_frame.f_code.co_filename
        if '/openlibrary' in cur_file:
            file_path = cur_file
        tback = tback.tb_next

    if file_path.endswith('template.py') and hasattr(exception, 'msg'):
        m = TEMPLATE_SYNTAX_ERROR_RE.search(exception.msg)
        if m:
            file_path = m.group(1)

    return file_path


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

    # Disabled temporarily (2020-04-07); they (the first two more specifically) looked
    # like they were causing too much load on graphite servers.
    # delegate.app.add_processor(web.loadhook(page_load_hook))
    # delegate.app.add_processor(web.unloadhook(page_unload_hook))
    # delegate.add_exception_hook(lambda: increment_error_count('ol.exceptions'))
