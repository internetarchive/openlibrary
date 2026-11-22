import json

import pytest

from openlibrary.plugins.worksearch import subject_counts as sc


def test_resolve_facet_field_maps_each_subject_type():
    assert sc.resolve_facet_field("subject") == "subject_facet"
    assert sc.resolve_facet_field("person") == "person_facet"
    assert sc.resolve_facet_field("place") == "place_facet"
    assert sc.resolve_facet_field("time") == "time_facet"


def test_resolve_facet_field_rejects_unknown_type():
    with pytest.raises(sc.InvalidSubjectQuery):
        sc.resolve_facet_field("works")  # not a facet; would be arbitrary field access


def test_batch_count_params_dereference_each_term():
    # No subject string may land in query syntax: each is bound to vN and read back via
    # {!term ... v=$vN}, so Solr matches it literally.
    params = sc.build_batch_count_params("subject_facet", ['Handbooks, "Manuals")', "B"])
    d = dict(params)
    facet = json.loads(d["json.facet"])
    assert facet["c0"]["q"] == "{!term f=subject_facet v=$v0}"
    assert facet["c1"]["q"] == "{!term f=subject_facet v=$v1}"
    # the raw strings are param values, not interpolated into the query
    assert ("v0", 'Handbooks, "Manuals")') in params
    assert ("v1", "B") in params


def test_enumerate_params_pick_sort_direction():
    asc = dict(sc.build_enumerate_params("subject_facet", 5, 10, ascending=True))
    facet = json.loads(asc["json.facet"])["s"]
    assert facet["sort"] == "count asc"
    assert facet["field"] == "subject_facet"
    assert facet["limit"] == 5
    assert facet["offset"] == 10
    assert facet["mincount"] == 1

    desc = dict(sc.build_enumerate_params("subject_facet", 5, 0, ascending=False))
    assert json.loads(desc["json.facet"])["s"]["sort"] == "count desc"


def test_contains_params_use_case_insensitive_substring():
    params = dict(sc.build_contains_params("subject_facet", "FiCtIoN", 2000, "index"))
    assert params["facet.contains"] == "FiCtIoN"
    assert params["facet.contains.ignoreCase"] == "true"
    assert params["facet.field"] == "subject_facet"
    assert params["facet.limit"] == 2000


def test_is_partial_reads_response_header():
    assert sc.is_partial({"responseHeader": {"partialResults": True}}) is True
    assert sc.is_partial({"responseHeader": {}}) is False
    assert sc.is_partial({}) is False


def _stub_solr(monkeypatch, response):
    monkeypatch.setattr(sc, "_run_solr", lambda params: response)


def test_batch_exact_count_returns_counts_in_order(monkeypatch):
    _stub_solr(
        monkeypatch,
        {"facets": {"c0": {"count": 3}, "c1": {"count": 1}}},
    )
    counts, partial = sc.batch_exact_count("subject_facet", ["A", "B"])
    assert counts == [3, 1]
    assert partial is False


def test_batch_exact_count_surfaces_partial(monkeypatch):
    _stub_solr(
        monkeypatch,
        {"responseHeader": {"partialResults": True}, "facets": {"c0": {"count": 9}}},
    )
    _, partial = sc.batch_exact_count("subject_facet", ["A"])
    assert partial is True


def test_enumerate_no_contains_uses_json_facet(monkeypatch):
    _stub_solr(
        monkeypatch,
        {"facets": {"s": {"numBuckets": 2, "buckets": [{"val": "X", "count": 2}, {"val": "Y", "count": 7}]}}},
    )
    items, has_more, partial = sc.enumerate_subjects("subject_facet", None, None, ascending=False, offset=0, limit=10)
    assert items == [("X", 2), ("Y", 7)]
    assert has_more is False  # numBuckets 2, both returned
    assert partial is False


def test_enumerate_no_contains_has_more_from_numbuckets(monkeypatch):
    _stub_solr(
        monkeypatch,
        {"facets": {"s": {"numBuckets": 50, "buckets": [{"val": "X", "count": 9}, {"val": "Y", "count": 7}]}}},
    )
    _, has_more, _ = sc.enumerate_subjects("subject_facet", None, None, ascending=False, offset=0, limit=2)
    assert has_more is True  # 50 distinct values, only 2 returned


def test_enumerate_max_works_filters_rare_tail(monkeypatch):
    _stub_solr(
        monkeypatch,
        {"facets": {"s": {"buckets": [{"val": "r", "count": 1}, {"val": "s", "count": 3}, {"val": "t", "count": 9}]}}},
    )
    items, has_more, _ = sc.enumerate_subjects("subject_facet", None, max_works=3, ascending=True, offset=0, limit=10)
    assert items == [("r", 1), ("s", 3)]
    assert has_more is False


def test_enumerate_contains_desc_has_more_from_probe_row(monkeypatch):
    _stub_solr(
        monkeypatch,
        {"facet_counts": {"facet_fields": {"subject_facet": ["A", 9, "B", 5, "C", 1]}}},
    )
    page, has_more, _ = sc.enumerate_subjects("subject_facet", "x", None, ascending=False, offset=0, limit=2)
    assert page == [("A", 9), ("B", 5)]
    assert has_more is True


def test_enumerate_contains_ascending_filters_and_sorts(monkeypatch):
    _stub_solr(
        monkeypatch,
        {"facet_counts": {"facet_fields": {"subject_facet": ["a fic", 5, "b fic", 1, "c fic", 3]}}},
    )
    items, _, _ = sc.enumerate_subjects("subject_facet", "fic", max_works=3, ascending=True, offset=0, limit=10)
    assert items == [("b fic", 1), ("c fic", 3)]  # count<=3, ascending


def test_enumerate_contains_ascending_refuses_when_match_set_exceeds_cap(monkeypatch):
    # A substring whose match set fills the scan cap can't yield a reliable rare tail.
    flat = []
    for n in range(sc.CONTAINS_SCAN_CAP):
        flat += [f"s{n}", 1]
    _stub_solr(monkeypatch, {"facet_counts": {"facet_fields": {"subject_facet": flat}}})
    with pytest.raises(sc.InvalidSubjectQuery):
        sc.enumerate_subjects("subject_facet", "e", max_works=1, ascending=True, offset=0, limit=10)


def test_flatten_facet_raises_subject_counts_unavailable_on_bad_shape():
    with pytest.raises(sc.SubjectCountsUnavailable):
        sc._flatten_facet({"error": {"msg": "boom"}}, "subject_facet")
