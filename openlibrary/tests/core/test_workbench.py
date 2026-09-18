"""Tests for openlibrary.core.workbench: filter → fq translation, query
parameters, row hydration with health chips, and worklists — with Solr and
the site faked."""

from unittest.mock import MagicMock

import pytest

from openlibrary.core import workbench
from openlibrary.utils.request_context import site


class FakeThing:
    def __init__(self, doc):
        self._doc = doc
        self.key = doc["key"]

    def dict(self):
        return dict(self._doc)


class FakeStore(dict):
    def values(self, **kw):
        return [v for v in dict.values(self) if v.get("type") == kw.get("type")]

    def delete(self, key):
        del self[key]


class FakeSite:
    def __init__(self, docs):
        self.docs = {d["key"]: dict(d) for d in docs}
        self.store = FakeStore()

    def get(self, key, revision=None):
        return FakeThing(self.docs[key]) if key in self.docs else None

    def get_many(self, keys, raw=False):
        return [FakeThing(self.docs[k]) for k in keys if k in self.docs]


WORK = {
    "key": "/works/OL1W",
    "type": {"key": "/type/work"},
    "title": "Shiloh",
    "authors": [{"author": {"key": "/authors/OL1A"}}],
    "subjects": ["Dogs"],
    "revision": 2,
}
ED_OK = {
    "key": "/books/OL1M",
    "type": {"key": "/type/edition"},
    "title": "Shiloh",
    "works": [{"key": "/works/OL1W"}],
    "authors": [{"key": "/authors/OL1A"}],
    "publishers": ["Atheneum"],
    "publish_date": "1991",
    "isbn_13": ["9780000000001"],
    "source_records": ["marc:x"],
    "revision": 3,
}
ED_BAD = {
    "key": "/books/OL2M",
    "type": {"key": "/type/edition"},
    "title": "Shiloh",
    "works": [{"key": "/works/OL1W"}],
    "authors": [{"key": "/authors/OL2A"}],
    "publish_date": "2099",
    "source_records": ["bwb:9780000000002"],
    "covers": [-1],
    "revision": 1,
}
AUTHOR = {"key": "/authors/OL1A", "type": {"key": "/type/author"}, "name": "Phyllis Reynolds Naylor", "remote_ids": {"viaf": "1"}, "revision": 1}
AUTHOR2 = {"key": "/authors/OL2A", "type": {"key": "/type/author"}, "name": "Naylor (illustrator)", "revision": 1}


@pytest.fixture(autouse=True)
def fakes(monkeypatch):
    s = FakeSite([WORK, ED_OK, ED_BAD, AUTHOR, AUTHOR2])
    site.set(s)
    solr = MagicMock()
    calls = []

    def select(params):
        calls.append(params)
        return {"docs": [{"key": "/books/OL1M", "cover_i": 5}, {"key": "/books/OL2M"}], "num_found": 2}

    monkeypatch.setattr(workbench, "_select", select)
    monkeypatch.setattr(workbench, "count_query_cached", lambda *a, **k: 7)
    return {"site": s, "solr": solr, "calls": calls}


def test_filters_translate_to_fq_and_page_checks():
    fqs, page = workbench.split_filters(
        "edition",
        [
            {"id": "no_cover"},
            {"id": "language", "value": "eng"},
            {"id": "year", "value": {"from": 1990, "to": ""}},
            {"id": "author", "value": "/authors/OL1A"},
            {"id": "author_mismatch"},
            {"id": "no_author"},  # work-only: dropped for editions
            {"id": "nope"},
        ],
    )
    assert fqs == ["-cover_i:*", 'language:"eng"', "publish_year:[1990 TO *]", "author_key:OL1A"]
    assert page == ["author_mismatch"]


def test_text_values_are_escaped():
    fqs, _ = workbench.split_filters("edition", [{"id": "publisher", "value": 'Foo "Bar"'}])
    assert fqs == ['publisher:"Foo \\"Bar\\""']


def test_query_params_free_text_vs_fielded():
    free = workbench._solr_params("edition", "tolkien hobbit", [], "relevance", 50, 0)
    assert free["defType"] == "edismax"
    assert free["fq"][0] == "type:edition"
    fielded = workbench._solr_params("work", "author_key:OL1A AND -ia:*", ["-cover_i:*"], "modified", 20, 40)
    assert "defType" not in fielded
    assert fielded["fq"] == ["type:work", "-cover_i:*"]
    assert fielded["sort"] == "last_modified_i desc"
    assert fielded["start"] == 40
    empty = workbench._solr_params("edition", "", [], "relevance", 50, 0)
    assert empty["q"] == "*:*"
    assert empty["sort"] == "title_sort asc"


def test_run_query_hydrates_rows_with_chips(fakes):
    out = workbench.run_query("edition", "shiloh", [{"id": "no_cover"}], "year_desc", page=2, rows=10)
    assert out["num_found"] == 2
    assert fakes["calls"][0]["start"] == 10
    ok, bad = out["records"]
    assert ok["key"] == "/books/OL1M"
    assert ok["authors"] == [{"key": "/authors/OL1A", "name": "Phyllis Reynolds Naylor"}]
    assert ok["work"]["title"] == "Shiloh"
    assert ok["cover"].endswith("/b/id/5-S.jpg")
    assert ok["chips"] == []
    codes = {c["code"] for c in bad["chips"]}
    assert codes == {"author_mismatch", "low_trust", "future_date", "placeholder_cover", "no_identifiers"}
    assert bad["sources"] == ["bwb"]


def test_page_filters_narrow_the_fetched_rows():
    out = workbench.run_query("edition", "", [{"id": "author_mismatch"}], "relevance")
    assert [r["key"] for r in out["records"]] == ["/books/OL2M"]
    assert out["page_filters"] == ["author_mismatch"]


def test_author_rows_flag_role_words_and_missing_ids(monkeypatch):
    monkeypatch.setattr(workbench, "_select", lambda params: {"docs": [{"key": "/authors/OL2A", "work_count": 3}], "num_found": 1})
    out = workbench.run_query("author", "naylor")
    row = out["records"][0]
    assert row["work_count"] == 3
    assert {c["code"] for c in row["chips"]} == {"role_in_name", "no_strong_ids"}


def test_hydrate_keys_groups_pasted_olids(monkeypatch):
    monkeypatch.setattr(workbench, "_select", lambda params: {"docs": [], "num_found": 0})
    out = workbench.hydrate_keys(["OL1M", "https://openlibrary.org/works/OL1W", "OL1A", "junk"])
    assert set(out) == {"edition", "work", "author"}
    assert out["work"][0]["subject_count"] == 1


def test_unknown_type_and_bad_worklist():
    with pytest.raises(workbench.WorkbenchError):
        workbench.run_query("subject", "x")
    with pytest.raises(workbench.WorkbenchError):
        workbench.save_worklist("me", {"name": "", "type": "edition"})


def test_worklists_round_trip(fakes):
    saved = workbench.save_worklist("me", {"name": "Mine", "type": "work", "q": "x", "filters": [{"id": "no_author"}, {"id": "nope"}], "sort": "readers"})
    assert saved["filters"] == [{"id": "no_author"}]
    assert saved["owner"] == "me"
    listed = workbench.list_worklists(with_counts=True)
    assert listed[0]["builtin"] is True
    assert listed[0]["count"] == 7
    assert next(w for w in listed if not w["builtin"])["id"] == saved["id"]
    with pytest.raises(workbench.WorkbenchError) as e:
        workbench.delete_worklist("someone-else", saved["id"])
    assert e.value.status == 403
    workbench.delete_worklist("someone-else", saved["id"], is_super=True)
    assert workbench.get_worklist(saved["id"]) is None
    assert workbench.get_worklist("orphan-works")["builtin"] is True
