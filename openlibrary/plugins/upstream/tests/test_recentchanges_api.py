"""Tests for the recentchanges JSON/YAML feed parameters (internetarchive/openlibrary#13860)."""

import json
from unittest.mock import Mock

import pytest
import web

from openlibrary.plugins.upstream import recentchanges


@pytest.fixture
def site(monkeypatch):
    site = Mock()
    site.recentchanges.return_value = []
    for name, value in {"site": site, "encoding": "json", "headers": [], "status": "200 OK"}.items():
        monkeypatch.setattr(web.ctx, name, value, raising=False)
    return site


def fetch(monkeypatch, site, query=None, **params):
    monkeypatch.setattr(web, "input", lambda **defaults: web.storage({**defaults, **params}))
    recentchanges.index().handle_encoding(dict(query or {}), "json")
    return site.recentchanges.call_args.args[0]


DAY = {"begin_date": "2026-08-28", "end_date": "2026-08-29", "kind": "edit-book"}


def test_no_begin_end_keeps_path_range(monkeypatch, site):
    query = fetch(monkeypatch, site, DAY)
    assert query == {**DAY, "limit": 100, "offset": 0}


def test_begin_end_inside_day(monkeypatch, site):
    query = fetch(monkeypatch, site, DAY, begin="2026-08-28T00:00:00", end="2026-08-28T01:00:00")
    assert query["begin_date"] == "2026-08-28T00:00:00"
    assert query["end_date"] == "2026-08-28T01:00:00"


def test_begin_end_clipped_to_path_day(monkeypatch, site):
    query = fetch(monkeypatch, site, DAY, begin="2026-08-01T00:00:00", end="2026-09-01T00:00:00")
    assert query["begin_date"] == "2026-08-28T00:00:00"
    assert query["end_date"] == "2026-08-29T00:00:00"


def test_only_begin_keeps_path_end(monkeypatch, site):
    query = fetch(monkeypatch, site, DAY, begin="2026-08-28T23:00:00")
    assert query["begin_date"] == "2026-08-28T23:00:00"
    assert query["end_date"] == "2026-08-29T00:00:00"


def test_begin_end_without_path_date(monkeypatch, site):
    query = fetch(monkeypatch, site, {"kind": "edit-book"}, begin="2026-08-28T05:00:00", end="2026-08-28T06:00:00")
    assert query["begin_date"] == "2026-08-28T05:00:00"
    assert query["end_date"] == "2026-08-28T06:00:00"


def test_timezone_aware_timestamps_normalised_to_utc(monkeypatch, site):
    query = fetch(monkeypatch, site, {}, begin="2026-08-28T05:00:00Z", end="2026-08-28T08:00:00+02:00")
    assert query["begin_date"] == "2026-08-28T05:00:00"
    assert query["end_date"] == "2026-08-28T06:00:00"


@pytest.mark.parametrize(
    "params",
    [
        {"begin": "yesterday"},
        {"end": "2026-13-01"},
        {"begin": "2026-08-28T02:00:00", "end": "2026-08-28T01:00:00"},
        {"begin": "2026-08-30T00:00:00"},  # entirely after the day in the path
        {"offset": "10001"},
    ],
)
def test_bad_requests(monkeypatch, site, params):
    with pytest.raises(web.HTTPError) as exc_info:
        fetch(monkeypatch, site, DAY, **params)
    assert exc_info.value.args[0] == "400 Bad Request"
    assert "error" in json.loads(exc_info.value.data)
    site.recentchanges.assert_not_called()


@pytest.mark.parametrize(
    ("params", "limit", "offset"),
    [
        ({"offset": "10000"}, 100, 10000),
        ({"offset": "-5"}, 100, 0),
        ({"limit": "5000"}, 1000, 0),
    ],
)
def test_limit_and_offset(monkeypatch, site, params, limit, offset):
    query = fetch(monkeypatch, site, DAY, **params)
    assert (query["limit"], query["offset"]) == (limit, offset)


def test_bot_and_author_unchanged(monkeypatch, site):
    query = fetch(monkeypatch, site, DAY, bot="true", author="/people/foo")
    assert query["bot"] is True
    assert query["author"] == "/people/foo"
