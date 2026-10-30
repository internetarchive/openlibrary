from openlibrary.admin import stats


def test_backfill_days_dont_inherit_a_later_days_counts(monkeypatch):
    "A key that has no figure for a past day (a snapshot, or a failed query) must be absent there, not copied back."
    calls = iter([{"saves": 3, "initiative_open_gaps": 40}, {"saves": 2}, {"saves": 1}])
    stored = {}
    monkeypatch.setattr(stats, "connect_to_pg", lambda config: None)
    monkeypatch.setattr(stats, "get_config_info", lambda config: None)
    monkeypatch.setattr(stats, "setup_ol_config", lambda config: None)
    monkeypatch.setattr(stats, "run_gathering_functions", lambda *args, prefix, **kw: next(calls) if prefix == "admin_range__" else {})
    monkeypatch.setattr(stats, "store_data", lambda data, date: stored.setdefault(date, []).append(dict(data)))

    assert stats.main("ib.yml", "ol.yml", "cs.yml", ndays=3) == 0

    # Each date's last store is its range row; today's first store is the totals.
    today, *past = [docs[-1] for _date, docs in sorted(stored.items(), reverse=True)]
    assert today == {"saves": 3, "initiative_open_gaps": 40}
    assert past == [{"saves": 2}, {"saves": 1}]
