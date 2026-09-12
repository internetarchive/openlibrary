"""Tests for openlibrary.core.record_context: key handling, redirect-safe loading
and the preview checks, against a fake infobase site."""

from unittest.mock import MagicMock

import pytest

from openlibrary.core import record_context as rc
from openlibrary.utils.request_context import site


class FakeThing:
    def __init__(self, doc):
        self._doc = doc
        self.key = doc["key"]

    def dict(self):
        return dict(self._doc)


class FakeSite:
    def __init__(self, docs):
        self.docs = {d["key"]: d for d in docs}

    def get(self, key, revision=None):
        return FakeThing(self.docs[key]) if key in self.docs else None

    def get_many(self, keys, raw=False):
        return [FakeThing(self.docs[k]) for k in keys if k in self.docs]

    def recentchanges(self, query):
        return []

    def things(self, query, details=False):
        return []


WORK = {"key": "/works/OL1W", "type": {"key": "/type/work"}, "title": "Shiloh", "authors": [{"author": {"key": "/authors/OL1A"}}], "revision": 3}
WORK2 = {"key": "/works/OL2W", "type": {"key": "/type/work"}, "title": "Other book", "authors": [{"author": {"key": "/authors/OL1A"}}], "revision": 1}
EDITION = {
    "key": "/books/OL1M",
    "type": {"key": "/type/edition"},
    "title": "Shiloh",
    "works": [{"key": "/works/OL1W"}],
    "authors": [{"key": "/authors/OL2A"}],
    "by_statement": "by Naylor",
    "revision": 2,
}
AUTHOR1 = {
    "key": "/authors/OL1A",
    "type": {"key": "/type/author"},
    "name": "Phyllis Reynolds Naylor",
    "birth_date": "1933",
    "remote_ids": {"wikidata": "Q1"},
    "revision": 1,
}
AUTHOR2 = {"key": "/authors/OL2A", "type": {"key": "/type/author"}, "name": "Jean Little", "birth_date": "1932", "remote_ids": {"wikidata": "Q2"}, "revision": 1}
REDIRECT = {"key": "/authors/OL9A", "type": {"key": "/type/redirect"}, "location": "/authors/OL1A"}


@pytest.fixture(autouse=True)
def fake_site(monkeypatch):
    s = FakeSite([WORK, WORK2, EDITION, AUTHOR1, AUTHOR2, REDIRECT])
    site.set(s)
    # Keep the checks local: no Wikidata, Solr, lists or reading-log lookups.
    monkeypatch.setattr(rc, "wikidata_for", lambda doc: None)
    monkeypatch.setattr(rc, "_solr_doc", lambda key, fields: {})
    monkeypatch.setattr(rc, "_lists_count", lambda key: 0)
    monkeypatch.setattr(rc, "_readinglog_count", lambda key: 0)
    return s


def test_normalize_key_accepts_olids_keys_and_urls():
    assert rc.normalize_key("OL1W") == "/works/OL1W"
    assert rc.normalize_key("/books/OL2M") == "/books/OL2M"
    assert rc.normalize_key("https://openlibrary.org/authors/OL3A/Name") == "/authors/OL3A"
    assert rc.normalize_key("OL1L") is None
    assert rc.normalize_key("") is None


def test_key_type_and_olid():
    assert rc.key_type("/works/OL1W") == "work"
    assert rc.key_type("/books/OL1M") == "edition"
    assert rc.key_type("/authors/OL1A") == "author"
    assert rc.olid("/works/OL1W") == "OL1W"


def test_load_docs_follows_redirects_and_reports_missing():
    docs, resolved, missing = rc.load_docs(["/authors/OL9A", "/works/OL1W", "/works/OL404W"])
    assert set(docs) == {"/authors/OL1A", "/works/OL1W"}
    assert resolved == {"/authors/OL9A": "/authors/OL1A"}
    assert missing == ["/works/OL404W"]


def test_ref_keys_handles_work_and_edition_shapes():
    assert rc.ref_keys(WORK["authors"]) == ["/authors/OL1A"]
    assert rc.ref_keys(EDITION["authors"]) == ["/authors/OL2A"]
    assert rc.ref_keys(None) == []


def test_check_merge_authors_blocks_on_different_wikidata_items():
    warnings = rc.check_merge_authors({AUTHOR1["key"]: AUTHOR1, AUTHOR2["key"]: AUTHOR2})
    codes = {w["code"]: w for w in warnings}
    assert codes["different_wikidata"]["level"] == "block"
    assert codes["primary"]["key"] == "/authors/OL1A"


def test_check_move_editions_flags_author_mismatch_and_already_there():
    # OL1M's own author (OL2A) is not among OL2W's (OL1A): a warn, never a block.
    warnings = rc.check_move_editions({EDITION["key"]: EDITION}, WORK2)
    assert [w["code"] for w in warnings] == ["author_mismatch", "title_mismatch"]
    assert all(w["level"] == "warn" for w in warnings)
    # Moving onto the work it is already on is only a note.
    already = rc.check_move_editions({EDITION["key"]: EDITION}, WORK)
    assert [w["code"] for w in already] == ["already_there"]


def test_check_merge_editions_blocks_when_works_differ():
    other = {**EDITION, "key": "/books/OL2M", "works": [{"key": "/works/OL2W"}]}
    warnings = rc.check_merge_editions({EDITION["key"]: EDITION, other["key"]: other})
    assert any(w["code"] == "different_works" and w["level"] == "block" for w in warnings)


def test_check_tag_warns_on_near_duplicate_subject():
    work = {**WORK, "subjects": ["Science fiction"]}
    warnings = rc.check_tag({work["key"]: work}, {"subjects": ["Science-fiction"]})
    assert warnings
    assert warnings[0]["code"] == "near_duplicate_subject"


def test_checks_for_never_raises(monkeypatch):
    monkeypatch.setattr(rc, "check_merge_works", MagicMock(side_effect=RuntimeError("boom")))
    warnings = rc.checks_for("merge_works", {WORK["key"]: WORK, WORK2["key"]: WORK2}, {})
    assert warnings == [{"level": "info", "code": "check_failed", "text": "Some checks couldn't run; nothing was verified automatically."}]


def test_smells_edition_without_work_and_future_date():
    ed = {**EDITION, "works": [], "publish_date": "2999"}
    codes = {c["code"] for c in rc._smells(ed, "edition")}
    assert {"future_date", "orphan_edition"} <= codes


def test_parse_source():
    assert rc.parse_source("bwb:9780000000000") == ("bwb", "Better World Books")
    assert rc.parse_source("marc:marc_loc_2016/BooksAll.2016.part01.utf8:1234") == ("marc", "MARC record")
    assert rc.parse_source("ia:shiloh00nayl") == ("ia", "Internet Archive")
