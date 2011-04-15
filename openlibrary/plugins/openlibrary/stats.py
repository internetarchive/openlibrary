"""Hooks for collecting performance stats.
"""
import web
from infogami.utils import stats
import openlibrary.core.stats

def stats_hook():
    """web.py unload hook to add X-OL-Stats header.
    
    This info can be written to lighttpd access log for collecting
    
    Also, send stats to graphite using statsd
    """
    stats_summary = stats.stats_summary()
    try:
        if "stats-header" in web.ctx.features:
            web.header("X-OL-Stats", format_stats(stats_summary))
    except Exception, e:
        # don't let errors in stats collection break the app.
        print >> web.debug, str(e)
        
    openlibrary.core.stats.increment('ol.pageviews')
    
    memcache_hits = 0
    memcache_misses = 0
    for s in web.ctx.get("stats", []):
        if s.name == 'memcache.get':
            if s.data['hit']:
                memcache_hits += 1
            else:
                memcache_misses += 1
    
    if memcache_hits:
        openlibrary.core.stats.increment('ol.memcache.hits', memcache_hits)
    if memcache_misses:
        openlibrary.core.stats.increment('ol.memcache.misses', memcache_misses)
    
    for name, value in stats_summary.items():
        name = name.replace(".", "_")
        time = value.get("time", 0.0) * 1000
        key  = 'ol.'+name
        openlibrary.core.stats.put(key, time)
    
def format_stats(stats):
    s = " ".join("%s %d %0.03f" % entry for entry in process_stats(stats))
    return '"%s"' %s

labels = {
    "total": "TT",
    "memcache": "MC",
    "infobase": "IB",
    "solr": "SR",
    "archive.org": "IA",
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