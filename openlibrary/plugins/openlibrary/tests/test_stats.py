from .. import stats

def test_format_stats_entry():
    stats.process_stats({"total": {"time": 0.1}}) == [("TT", 0, 0.1)]
    stats.process_stats({"total": {"time": 0.1346}}) == [("TT", 0, 0.135)]
    
    stats.process_stats({"memcache": {"count": 2, "time": 0.1}}) == [("MC", 2, 0.100)]    
    stats.process_stats({"infobase": {"count": 2, "time": 0.1}}) == [("IB", 2, 0.100)]
    stats.process_stats({"couchdb": {"count": 2, "time": 0.1}}) == [("CD", 2, 0.100)]
    stats.process_stats({"solr": {"count": 2, "time": 0.1}}) == [("SR", 2, 0.100)]
    stats.process_stats({"archive.org": {"count": 2, "time": 0.1}}) == [("IA", 2, 0.100)]
    stats.process_stats({"something-else": {"count": 2, "time": 0.1}}) == [("OT", 2, 0.100)]

def test_format_stats():
    stats.format_stats({"total": {"time": 0.2}, "infobase": {"count": 2, "time": 0.13}}) == '"IB 2 0.130 TT 0 0.200"'
    