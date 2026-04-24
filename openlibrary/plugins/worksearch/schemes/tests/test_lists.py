from openlibrary.plugins.worksearch.schemes.lists import ListSearchScheme


def test_q_to_solr_params_includes_qf():
    s = ListSearchScheme()
    params = dict(s.q_to_solr_params("library journal", set(), []))
    assert params["qf"] == "text name^10"
    assert params["defType"] == "edismax"
    assert params["q.op"] == "AND"


def test_q_to_solr_params_seed_count_filter_added_by_default():
    s = ListSearchScheme()
    params = s.q_to_solr_params("library journal", set(), [])
    fq_values = [v for k, v in params if k == "fq"]
    assert "seed_count:[2 TO *] OR list_type:series" in fq_values


def test_q_to_solr_params_seed_count_filter_skipped_when_queried():
    s = ListSearchScheme()
    params = s.q_to_solr_params("seed_count:[5 TO *]", set(), [])
    fq_values = [v for k, v in params if k == "fq"]
    assert not fq_values
