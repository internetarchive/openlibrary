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


def test_exact_count_params_dereference_the_term():
    # The raw subject must never land in query syntax: it is bound to `subj` and
    # read back via {!term ... v=$subj}, so Solr matches it literally.
    params = dict(sc.build_exact_count_params("subject_facet", 'Handbooks, "Manuals")'))
    assert params["fq"] == "{!term f=subject_facet v=$subj}"
    assert params["subj"] == 'Handbooks, "Manuals")'
    assert params["rows"] == 0


def test_enumerate_params_pick_sort_direction():
    asc = dict(sc.build_enumerate_params("subject_facet", 5, 10, ascending=True))
    import json

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


def test_postprocess_filters_by_max_works_and_sorts_ascending():
    pairs = [("a", 5), ("b", 1), ("c", 3), ("d", 9)]
    items, has_more, truncated = sc.postprocess_contains(pairs, max_works=3, ascending=True, offset=0, limit=10, scan_cap=2000)
    assert items == [("b", 1), ("c", 3)]
    assert has_more is False
    assert truncated is False


def test_postprocess_reports_truncation_at_scan_cap():
    pairs = [(f"s{i}", 1) for i in range(5)]
    _, _, truncated = sc.postprocess_contains(pairs, max_works=None, ascending=True, offset=0, limit=10, scan_cap=5)
    assert truncated is True


def test_postprocess_pages_with_offset_and_limit():
    pairs = [("a", 1), ("b", 2), ("c", 3), ("d", 4)]
    items, has_more, _ = sc.postprocess_contains(pairs, max_works=None, ascending=True, offset=1, limit=2, scan_cap=2000)
    assert items == [("b", 2), ("c", 3)]
    assert has_more is True  # "d" remains after this page


def _stub_solr(monkeypatch, response):
    monkeypatch.setattr(sc, "_run_solr", lambda params: response)


def test_enumerate_no_contains_uses_json_facet(monkeypatch):
    _stub_solr(
        monkeypatch,
        {"facets": {"s": {"buckets": [{"val": "X", "count": 2}, {"val": "Y", "count": 7}]}}},
    )
    items, has_more, truncated = sc.enumerate_subjects("subject_facet", None, None, ascending=False, offset=0, limit=10)
    assert items == [("X", 2), ("Y", 7)]
    assert truncated is False
    assert has_more is False  # fewer buckets than the limit


def test_enumerate_max_works_filters_rare_tail(monkeypatch):
    # Count-ascending buckets; the cutoff is 3, so the 9-count value drops off and the
    # short page signals the tail is exhausted.
    _stub_solr(
        monkeypatch,
        {"facets": {"s": {"buckets": [{"val": "r", "count": 1}, {"val": "s", "count": 3}, {"val": "t", "count": 9}]}}},
    )
    items, has_more, _ = sc.enumerate_subjects("subject_facet", None, max_works=3, ascending=True, offset=0, limit=10)
    assert items == [("r", 1), ("s", 3)]
    assert has_more is False


def test_enumerate_no_contains_has_more_from_numbuckets(monkeypatch):
    _stub_solr(
        monkeypatch,
        {"facets": {"s": {"numBuckets": 50, "buckets": [{"val": "X", "count": 9}, {"val": "Y", "count": 7}]}}},
    )
    _, has_more, _ = sc.enumerate_subjects("subject_facet", None, None, ascending=False, offset=0, limit=2)
    assert has_more is True  # 50 distinct values, only 2 returned


def test_enumerate_contains_desc_has_more_from_probe_row(monkeypatch):
    # The desc path fetches offset+limit+1 rows; the extra row means another page exists.
    _stub_solr(
        monkeypatch,
        {"facet_counts": {"facet_fields": {"subject_facet": ["A", 9, "B", 5, "C", 1]}}},
    )
    page, has_more, truncated = sc.enumerate_subjects("subject_facet", "x", None, ascending=False, offset=0, limit=2)
    assert page == [("A", 9), ("B", 5)]
    assert has_more is True
    assert truncated is False


def test_enumerate_contains_flattens_classic_facet(monkeypatch):
    _stub_solr(
        monkeypatch,
        {"facet_counts": {"facet_fields": {"subject_facet": ["A fiction", 1, "B fiction", 4]}}},
    )
    items, _, _ = sc.enumerate_subjects("subject_facet", "fiction", None, ascending=False, offset=0, limit=10)
    assert items == [("B fiction", 4), ("A fiction", 1)]  # count descending
