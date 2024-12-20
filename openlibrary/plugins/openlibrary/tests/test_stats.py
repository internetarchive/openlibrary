"""
Tests the stats gathering systems.
"""

import calendar
import datetime

from openlibrary.core.admin import Stats

from .. import stats


class MockDoc(dict):
    def __init__(self, _id, *largs, **kargs):
        self.id = _id
        kargs['_key'] = _id
        super().__init__(*largs, **kargs)

    def __repr__(self):
        o = super().__repr__()
        return f"<{self.id} - {o}>"


def test_format_stats_entry():
    "Tests the stats performance entries"
    ps = stats.process_stats
    assert ps({"total": {"time": 0.1}}) == [("TT", 0, 0.1)]
    # assert ps({"total": {"time": 0.1346}}) == [("TT", 0, 0.135)]  # FIXME

    assert ps({"memcache": {"count": 2, "time": 0.1}}) == [("MC", 2, 0.100)]
    assert ps({"infobase": {"count": 2, "time": 0.1}}) == [("IB", 2, 0.100)]
    assert ps({"couchdb": {"count": 2, "time": 0.1}}) == [("CD", 2, 0.100)]
    assert ps({"solr": {"count": 2, "time": 0.1}}) == [("SR", 2, 0.100)]
    # assert ps({"archive.org": {"count": 2, "time": 0.1}}) == [("IA", 2, 0.100)]  # FIXME
    assert ps({"something-else": {"count": 2, "time": 0.1}}) == [("OT", 2, 0.100)]


def test_format_stats():
    "Tests whether the performance status are output properly in the the X-OL-Stats header"
    performance_stats = {"total": {"time": 0.2}, "infobase": {"count": 2, "time": 0.13}}
    assert stats.format_stats(performance_stats) == '"IB 2 0.130 TT 0 0.200"'


def test_stats_container():
    "Tests the Stats container used in the templates"
    # Test basic API and null total count
    ipdata = [{"foo": 1}] * 100
    s = Stats(ipdata, "foo", "nothing")
    expected_op = [(x, 1) for x in range(0, 140, 5)]
    assert list(s.get_counts()) == expected_op
    assert s.get_summary() == 28
    assert s.total == ""


def test_status_total():
    "Tests the total attribute of the stats container used in the templates"
    ipdata = [{"foo": 1, "total": x * 2} for x in range(1, 100)]
    s = Stats(ipdata, "foo", "total")
    assert s.total == 198
    # Test a total before the last
    ipdata = [{"foo": 1, "total": x * 2} for x in range(1, 100)]
    for i in range(90, 99):
        del ipdata[i]["total"]
        ipdata[90]["total"] = 2
    s = Stats(ipdata, "foo", "total")
    assert s.total == 2


def test_status_timerange():
    "Tests the stats container with a time X-axis"
    d = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    ipdata = []
    expected_op = []
    for i in range(10):
        doc = MockDoc(_id=d.strftime("counts-%Y-%m-%d"), foo=1)
        ipdata.append(doc)
        expected_op.append([calendar.timegm(d.timetuple()) * 1000, 1])
        d += datetime.timedelta(days=1)
    s = Stats(ipdata, "foo", "nothing")
    assert s.get_counts(10, True) == expected_op[:10]
