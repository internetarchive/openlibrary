"""Hooks for collecting performance stats.
"""
import web
from infogami.utils import stats

def stats_hook():
    """web.py unload hook to add X-OL-Stats header.
    
    This info can be written to lighttpd access log for collecting
    """
    try:
        if "stats-header" in web.ctx.features:
            web.header("X-OL-Stats", format_stats(stats.stats_summary()))
    except Exception, e:
        # don't let errors in stats collection break the app.
        print >> web.debug, str(e)
        
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