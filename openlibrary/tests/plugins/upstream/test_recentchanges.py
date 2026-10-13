"""Tests for the begin/end window of the recentchanges JSON and YAML feeds
(internetarchive/openlibrary#13860)."""

from unittest import mock

import pytest
import web

from openlibrary.plugins.upstream.recentchanges import index


@pytest.fixture
def site(monkeypatch):
    site = mock.Mock()
    site.recentchanges.return_value = []
    monkeypatch.setattr(web.ctx, "site", site, raising=False)
    monkeypatch.setattr(web.ctx, "status", "200 OK", raising=False)
    monkeypatch.setattr(web.ctx, "headers", [], raising=False)
    return site


def get_feed(monkeypatch, **params):
    monkeypatch.setattr(web, "input", lambda **defaults: web.storage({**defaults, **params}))
    return index().handle_encoding({}, "json")


def test_begin_and_end_are_passed_to_the_query(monkeypatch, site):
    get_feed(monkeypatch, begin="2026-08-28T00:00:00", end="2026-08-28T01:00:00")
    query = site.recentchanges.call_args[0][0]
    assert query["begin_date"] == "2026-08-28T00:00:00"
    assert query["end_date"] == "2026-08-28T01:00:00"


def test_feed_without_begin_and_end_is_unchanged(monkeypatch, site):
    get_feed(monkeypatch)
    query = site.recentchanges.call_args[0][0]
    assert "begin_date" not in query
    assert "end_date" not in query


@pytest.mark.parametrize("param", ["begin", "end"])
def test_invalid_timestamp_is_a_bad_request(monkeypatch, site, param):
    get_feed(monkeypatch, **{param: "yesterday"})
    assert web.ctx.status.startswith("400")
    site.recentchanges.assert_not_called()
