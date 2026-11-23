from openlibrary.admin import stats


def test_backfill_days_dont_inherit_a_later_days_counts(monkeypatch):
    "A key that has no figure for a past day (a snapshot, or a failed query) must be absent there, not copied back."
    calls = iter([{"saves": 3, "initiative_open_gaps": 40}, {"saves": 2}, {"saves": 1}])
    stored = {}
    monkeypatch.setattr(stats, "pg_parameters", lambda config: {})
    monkeypatch.setattr(stats, "connect_to_pg", lambda config: None)
    monkeypatch.setattr(stats, "setup_ol_config", lambda config: None)
    monkeypatch.setattr(stats, "run_gathering_functions", lambda *args, prefix, **kw: next(calls) if prefix == "admin_range__" else {})
    monkeypatch.setattr(stats, "store_data", lambda data, date: stored.setdefault(date, []).append(dict(data)))

    assert stats.main("ib.yml", "ol.yml", "cs.yml", ndays=3) == 0

    # Each date's last store is its range row; today's first store is the totals.
    today, *past = [docs[-1] for _date, docs in sorted(stored.items(), reverse=True)]
    assert today == {"saves": 3, "initiative_open_gaps": 40}
    assert past == [{"saves": 2}, {"saves": 1}]


def test_pg_parameters_pass_port_and_password(tmp_path):
    "Both key styles in the production configs (infobase.yml and coverstore.yml) keep host, port and password."
    infobase_yml = tmp_path / "infobase.yml"
    infobase_yml.write_text("db_parameters:\n  engine: postgres\n  host: db\n  database: openlibrary\n  username: ol\n  password: secret\n  port: 6432\n")
    coverstore_yml = tmp_path / "coverstore.yml"
    coverstore_yml.write_text("db_parameters:\n  dbn: postgres\n  host: db\n  db: coverstore\n  user: ol\n  pw: secret\n  port: 6432\n")

    assert stats.pg_parameters(infobase_yml) == {"db": "openlibrary", "user": "ol", "pw": "secret", "host": "db", "port": 6432}
    assert stats.pg_parameters(coverstore_yml) == {"db": "coverstore", "user": "ol", "pw": "secret", "host": "db", "port": 6432}
