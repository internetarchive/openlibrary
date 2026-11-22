import asyncio
import json

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from openlibrary.fastapi import subject_counts as sc

app = FastAPI()
app.include_router(sc.router)
client = TestClient(app)

URL = "/search/subjects/counts.json"


def _mock_solr(monkeypatch, response):
    async def stub(params):
        return response

    monkeypatch.setattr(sc, "_run_solr", stub)


# --- pure query builders (injection boundary, Solr directives) ---


def test_batch_count_params_dereference_each_term():
    # No subject string may land in query syntax: each is bound to vN and read back via
    # {!term ... v=$vN}, so Solr matches it literally.
    params = sc.build_batch_count_params("subject_facet", ['Handbooks, "Manuals")', "B"])
    facet = json.loads(dict(params)["json.facet"])
    assert facet["c0"]["q"] == "{!term f=subject_facet v=$v0}"
    assert facet["c1"]["q"] == "{!term f=subject_facet v=$v1}"
    assert ("v0", 'Handbooks, "Manuals")') in params
    assert ("v1", "B") in params


def test_enumerate_params_pick_sort_direction():
    asc = json.loads(dict(sc.build_enumerate_params("subject_facet", 5, 10, True))["json.facet"])["s"]
    assert (asc["sort"], asc["limit"], asc["offset"], asc["mincount"]) == ("count asc", 5, 10, 1)
    desc = json.loads(dict(sc.build_enumerate_params("subject_facet", 5, 0, False))["json.facet"])["s"]
    assert desc["sort"] == "count desc"


def test_contains_params_use_case_insensitive_substring():
    params = dict(sc.build_contains_params("subject_facet", "FiCtIoN", 2000, "index"))
    assert params["facet.contains"] == "FiCtIoN"
    assert params["facet.contains.ignoreCase"] == "true"
    assert params["facet.limit"] == 2000


def test_is_partial_reads_response_header():
    assert sc.is_partial({"responseHeader": {"partialResults": True}}) is True
    assert sc.is_partial({"responseHeader": {}}) is False
    assert sc.is_partial({}) is False


def test_flatten_facet_raises_503_on_bad_shape():
    with pytest.raises(HTTPException) as exc:
        sc._flatten_facet({"error": {"msg": "boom"}}, "subject_facet")
    assert exc.value.status_code == 503


# --- _run_solr error mapping (the 503 path) ---


def test_run_solr_maps_http_error_to_503(monkeypatch):
    class _Resp:
        def raise_for_status(self):
            raise httpx.HTTPError("boom")

    class _Solr:
        async def raw_request(self, path, payload):
            return _Resp()

    monkeypatch.setattr(sc, "get_solr", _Solr)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(sc._run_solr([("q", "*:*")]))
    assert exc.value.status_code == 503


def test_run_solr_maps_non_json_to_503(monkeypatch):
    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            raise ValueError("not json")

    class _Solr:
        async def raw_request(self, path, payload):
            return _Resp()

    monkeypatch.setattr(sc, "get_solr", _Solr)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(sc._run_solr([("q", "*:*")]))
    assert exc.value.status_code == 503


# --- the HTTP route: exact and batch ---


def test_exact_single_returns_object(monkeypatch):
    _mock_solr(monkeypatch, {"facets": {"c0": {"count": 3}}})
    r = client.get(URL, params={"subject": "Handbooks, Manuals"})
    assert r.status_code == 200
    assert r.json() == {
        "subject_type": "subject",
        "subject": "Handbooks, Manuals",
        "work_count": 3,
        "partial": False,
    }


def test_exact_batch_returns_list_in_order(monkeypatch):
    _mock_solr(monkeypatch, {"facets": {"c0": {"count": 3}, "c1": {"count": 1}}})
    r = client.get(URL, params=[("subject", "A"), ("subject", "B")])
    assert r.status_code == 200
    body = r.json()
    assert body["subjects"] == [
        {"subject": "A", "work_count": 3},
        {"subject": "B", "work_count": 1},
    ]


def test_exact_surfaces_partial(monkeypatch):
    _mock_solr(monkeypatch, {"responseHeader": {"partialResults": True}, "facets": {"c0": {"count": 9}}})
    assert client.get(URL, params={"subject": "X"}).json()["partial"] is True


# --- the HTTP route: enumerate ---


def test_enumerate_no_contains(monkeypatch):
    _mock_solr(
        monkeypatch,
        {"facets": {"s": {"numBuckets": 50, "buckets": [{"val": "X", "count": 9}, {"val": "Y", "count": 7}]}}},
    )
    body = client.get(URL, params={"limit": 2}).json()
    assert [(s["subject"], s["work_count"]) for s in body["subjects"]] == [("X", 9), ("Y", 7)]
    assert body["has_more"] is True  # 50 distinct, 2 returned


def test_enumerate_contains_desc(monkeypatch):
    _mock_solr(monkeypatch, {"facet_counts": {"facet_fields": {"subject_facet": ["A", 9, "B", 5, "C", 1]}}})
    body = client.get(URL, params={"contains": "fic", "limit": 2}).json()
    assert [(s["subject"], s["work_count"]) for s in body["subjects"]] == [("A", 9), ("B", 5)]
    assert body["has_more"] is True


def test_enumerate_contains_rare_tail_ascending(monkeypatch):
    _mock_solr(
        monkeypatch,
        {"facet_counts": {"facet_fields": {"subject_facet": ["a fic", 5, "b fic", 1, "c fic", 3]}}},
    )
    body = client.get(URL, params={"contains": "fic", "max_works": 3}).json()
    assert [(s["subject"], s["work_count"]) for s in body["subjects"]] == [("b fic", 1), ("c fic", 3)]
    assert body["sort"] == "count_asc"


def test_enumerate_max_works_no_contains(monkeypatch):
    _mock_solr(
        monkeypatch,
        {"facets": {"s": {"buckets": [{"val": "r", "count": 1}, {"val": "s", "count": 3}, {"val": "t", "count": 9}]}}},
    )
    body = client.get(URL, params={"max_works": 3}).json()
    assert [(s["subject"], s["work_count"]) for s in body["subjects"]] == [("r", 1), ("s", 3)]


def test_rare_tail_too_broad_refused_400(monkeypatch):
    flat = []
    for n in range(sc.CONTAINS_SCAN_CAP):
        flat += [f"s{n}", 1]
    _mock_solr(monkeypatch, {"facet_counts": {"facet_fields": {"subject_facet": flat}}})
    r = client.get(URL, params={"contains": "ee", "max_works": 1})
    assert r.status_code == 400


# --- the HTTP route: validation guards (item 1) ---


@pytest.mark.parametrize(
    "params",
    [
        {"subject_type": "works"},  # not a facet
        {"limit": 0},  # below min
        {"limit": 2000},  # above max
        {"offset": -1},  # negative
        {"offset": 9999, "limit": 1000},  # window exceeded
        {"contains": "a"},  # below min length
        {"max_works": -1},  # negative
        {"subject": ""},  # blank exact subject
    ],
)
def test_validation_guards_return_422(params):
    assert client.get(URL, params=params).status_code == 422


def test_batch_over_cap_returns_422():
    many = [("subject", f"s{i}") for i in range(sc.MAX_BATCH + 1)]
    assert client.get(URL, params=many).status_code == 422


def test_overlong_subject_and_contains_return_422():
    assert client.get(URL, params={"subject": "x" * (sc.MAX_SUBJECT_LEN + 1)}).status_code == 422
    assert client.get(URL, params={"contains": "y" * (sc.MAX_CONTAINS_LEN + 1)}).status_code == 422


def test_malformed_json_facet_batch_maps_to_503(monkeypatch):
    # A malformed Solr reply (facets present but a bucket is not a dict) must become a
    # sanitized 503, not an uncaught 500 — the same contract as the classic facet path.
    _mock_solr(monkeypatch, {"facets": {"c0": "oops"}})
    assert client.get(URL, params={"subject": "A"}).status_code == 503


def test_malformed_json_facet_enumerate_maps_to_503(monkeypatch):
    _mock_solr(monkeypatch, {"facets": {"s": {"buckets": [{"no_val": 1}]}}})
    assert client.get(URL, params={"limit": 5}).status_code == 503
