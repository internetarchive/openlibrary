from unittest.mock import patch

import web

from openlibrary.plugins.worksearch.code import (
    SearchResponse,
    _get_readable_count,
    _prepare_solr_query_params,
    describe_solr_query,
    get_doc,
    process_facet,
)
from openlibrary.plugins.worksearch.schemes.works import WorkSearchScheme
from openlibrary.utils.request_context import RequestContextVars, req_context


def test_process_facet():
    facets = [("false", 46), ("true", 2)]
    assert list(process_facet("has_fulltext", facets)) == [
        ("true", "yes", 2),
        ("false", "no", 46),
    ]


def test_get_doc():
    doc = get_doc(
        {
            "author_key": ["OL218224A"],
            "author_name": ["Alan Freedman"],
            "cover_edition_key": "OL1111795M",
            "cover_i": 6426606,
            "edition_count": 14,
            "first_publish_year": 1981,
            "has_fulltext": True,
            "ia": ["computerglossary00free"],
            "key": "/works/OL1820355W",
            "lending_edition_s": "OL1111795M",
            "public_scan_b": False,
            "title": "The computer glossary",
            "ratings_average": None,
            "ratings_count": None,
            "want_to_read_count": None,
        }
    )
    assert doc == web.storage(
        {
            "key": "/works/OL1820355W",
            "title": "The computer glossary",
            "url": "/works/OL1820355W/The_computer_glossary",
            "edition_count": 14,
            "ia": ["computerglossary00free"],
            "collections": [],
            "has_fulltext": True,
            "public_scan": False,
            "lending_edition": "OL1111795M",
            "lending_identifier": None,
            "authors": [
                web.storage(
                    {
                        "key": "OL218224A",
                        "name": "Alan Freedman",
                        "url": "/authors/OL218224A/Alan_Freedman",
                        "birth_date": None,
                        "death_date": None,
                    }
                )
            ],
            "first_publish_year": 1981,
            "first_edition": None,
            "subtitle": None,
            "cover_edition_key": "OL1111795M",
            "cover_i": 6426606,
            "languages": [],
            "id_project_gutenberg": [],
            "id_project_runeberg": [],
            "id_librivox": [],
            "id_standard_ebooks": [],
            "id_openstax": [],
            "id_cita_press": [],
            "id_wikisource": [],
            "editions": [],
            "ratings_average": None,
            "ratings_count": None,
            "want_to_read_count": None,
            "series": [],
        }
    )


def test_prepare_solr_query_params_first_publish_year_string():
    """Test to check that when we have a facet value as a string it is converted to a list properly"""
    scheme = WorkSearchScheme()
    param = {"first_publish_year": "1997"}
    params, fields = _prepare_solr_query_params(scheme, param)

    param2 = {"first_publish_year": ["1997"]}
    params2, fields2 = _prepare_solr_query_params(scheme, param2)
    assert params == params2
    assert fields == fields2
    # Check that the fq param for first_publish_year is correctly added
    fq_params = [p for p in params if p[0] == "fq"]
    assert ("fq", 'first_publish_year:"1997"') in fq_params


def _editions_fq_for(param: dict) -> list[str]:
    """Run a Solr-editions query for `param` and return its editions.fq clauses.

    Sets req_context because the has_fulltext facet_rewrite resolves
    get_fulltext_min() off it; requesting the `editions` field opts the query
    into the block-join path that builds editions.fq. convert_iso_to_marc is
    stubbed since it reaches for the `site` ContextVar (irrelevant here)."""
    token = req_context.set(
        RequestContextVars(
            x_forwarded_for=None,
            user_agent=None,
            lang="en",
            solr_editions=True,
            print_disabled=False,
        )
    )
    try:
        scheme = WorkSearchScheme(solr_editions=True)
        with patch(
            "openlibrary.plugins.worksearch.schemes.works.convert_iso_to_marc",
            return_value="eng",
        ):
            params, _ = _prepare_solr_query_params(scheme, param, fields="key,editions")
    finally:
        req_context.reset(token)
    return [v for k, v in params if k == "editions.fq"]


def test_prepare_solr_query_params_borrowable_editions_fq_anchors_negation():
    """ "Borrowable Only" maps to has_fulltext=true + public_scan=false, the
    latter rewriting to a negated `-ebook_access:public`. A bare pure-negative
    clause matches nothing inside the block-join `filters=$editions.fq` local
    param (no top-level `*:*` fixup), which made the filter return zero results.
    It must be anchored as `(*:* -ebook_access:public)`."""
    editions_fq = _editions_fq_for({"q": "harry potter", "has_fulltext": "true", "public_scan": "false"})
    assert "(*:* -ebook_access:public)" in editions_fq
    # The unanchored form (the bug) must never be emitted.
    assert "-ebook_access:public" not in editions_fq


def test_prepare_solr_query_params_open_access_editions_fq_positive_unwrapped():
    """A positive availability clause ("Free to read now" → public_scan=true →
    ebook_access:public) must pass through to editions.fq unwrapped — the
    negation guard should only touch negated clauses."""
    editions_fq = _editions_fq_for({"q": "harry potter", "public_scan": "true"})
    assert "ebook_access:public" in editions_fq
    assert "(*:* -ebook_access:public)" not in editions_fq


def test_prepare_solr_query_params_multiple_languages_or_into_single_fq():
    """Multiple selected languages are additive: a work in *any* of them should
    match, so they must be OR-ed into one fq. Emitting one fq per value AND-s
    them (Solr ANDs separate fqs), which would require a work to be in every
    selected language at once."""
    scheme = WorkSearchScheme()
    params, _ = _prepare_solr_query_params(scheme, {"q": "1984", "language": ["eng", "spa"]})
    fqs = [v for k, v in params if k == "fq"]
    assert 'language:("eng" OR "spa")' in fqs
    # Never emitted as two separate (AND-ed) clauses.
    assert 'language:"eng"' not in fqs
    assert 'language:"spa"' not in fqs


def test_prepare_solr_query_params_language_mirrored_into_editions_fq():
    """The language constraint must reach editions.fq so a work matches only
    when the *same edition* is in a selected language. Without this, "English"
    + "Borrowable" could match a work through a Chinese borrowable edition —
    the cross-edition leak this filtering fixes. The OR-clause keeps the field
    name first so the editions.fq `split(":", 1)` still resolves `language`."""
    editions_fq = _editions_fq_for({"q": "1984", "language": ["eng", "spa"]})
    assert 'language:("eng" OR "spa")' in editions_fq


def _with_req_context(fn):
    """Run `fn` with a req_context set (the readable-count query reads
    solr_editions off it)."""
    token = req_context.set(
        RequestContextVars(
            x_forwarded_for=None,
            user_agent=None,
            lang="en",
            solr_editions=True,
            print_disabled=False,
        )
    )
    try:
        return fn()
    finally:
        req_context.reset(token)


def test_get_readable_count_returns_none_when_nothing_to_count():
    """No active search, or a zero-result search, yields no sublabel (None)."""
    assert _get_readable_count({}, web.storage(num_found=0)) is None
    assert _get_readable_count({"q": "x"}, web.storage(num_found=0)) is None
    assert _get_readable_count({}, web.storage(num_found=5)) is None


def test_get_readable_count_reuses_num_found_when_already_readable():
    """When the search is already readable-scoped (has_fulltext=true), the main
    result count IS the readable count — no extra Solr query is issued."""
    with patch("openlibrary.plugins.worksearch.code.run_solr_query") as mock_query:
        count = _get_readable_count(
            {"q": "harry potter", "has_fulltext": "true"},
            web.storage(num_found=123),
        )
    assert count == 123
    mock_query.assert_not_called()


def test_get_readable_count_queries_with_readable_filter_when_toggle_off():
    """When the toggle is off (all books), a count-only query is run with
    has_fulltext forced on and public_scan stripped, and its num_found returned."""

    def run():
        with patch(
            "openlibrary.plugins.worksearch.code.run_solr_query",
            return_value=web.storage(num_found=42),
        ) as mock_query:
            count = _get_readable_count(
                {"q": "harry potter", "public_scan": "true"},
                web.storage(num_found=100),
            )
        return count, mock_query

    count, mock_query = _with_req_context(run)
    assert count == 42
    mock_query.assert_called_once()
    readable_param = mock_query.call_args.args[1]
    assert readable_param["has_fulltext"] == "true"
    assert "public_scan" not in readable_param
    assert mock_query.call_args.kwargs["rows"] == 0


def test_describe_solr_query_omits_user_query_text():
    """The shape is logged to Sentry, so it must not carry what the patron typed."""
    secret = "my private search terms"
    shape = describe_solr_query(
        "/solr/openlibrary/select",
        [
            ("q", "({!edismax v=$workQuery})"),
            ("workQuery", secret),
            ("ol.label", "WorkSearch"),
            ("fq", "type:work"),
            ("fq", "author_key:OL874808A"),
            ("start", "0"),
            ("rows", "20"),
        ],
    )
    assert secret not in repr(shape)
    assert shape["label"] == "WorkSearch"
    # Field names are kept; the values they filter on are not.
    assert shape["fq_fields"] == ["author_key", "type"]
    assert "OL874808A" not in repr(shape)


def test_describe_solr_query_flags_expensive_shapes():
    shape = describe_solr_query(
        "/solr/openlibrary/select",
        [
            ("ol.label", "ReadingLog"),
            ("q", "key:(/works/OL1W OR /works/OL2W OR /works/OL3W)"),
            ("start", "100000"),
            ("rows", "100"),
            ("facet.field", "subject_facet"),
            ("facet.field", "person_facet"),
            ("spellcheck", "true"),
        ],
    )
    # Deep paging and large boolean queries are the usual culprits.
    assert shape["start"] == 100000
    assert shape["or_clauses"] == 2
    assert shape["facet_fields"] == 2
    assert shape["spellcheck"] is True


def test_describe_solr_query_detects_block_join():
    shape = describe_solr_query(
        "/solr/openlibrary/select",
        [
            ("q", '_query_:"{!parent which=type:work v=$fullEdQuery}"'),
            ("fl", "key,editions:[subquery]"),
        ],
    )
    assert shape["block_join"] is True
    assert shape["subquery"] is True
    assert shape["label"] == "UNLABELLED"


def test_search_response_flags_partial_results():
    """Solr returns 200 + partialResults when it gives up early; don't swallow it."""
    solr_result = {
        "responseHeader": {"QTime": 10001, "partialResults": True},
        "response": {"docs": [{"key": "/works/OL1W"}], "numFound": 1},
    }
    resp = SearchResponse.from_solr_result(solr_result, "", "", time=10.5)
    assert resp.partial_results is True
    assert resp.num_found == 1


def test_search_response_partial_results_accepts_string_flag():
    solr_result = {
        "responseHeader": {"partialResults": "true"},
        "response": {"docs": [], "numFound": 0},
    }
    assert SearchResponse.from_solr_result(solr_result, "", "", time=1.0).partial_results is True


def test_search_response_complete_results_not_flagged_partial():
    solr_result = {
        "responseHeader": {"QTime": 12},
        "response": {"docs": [], "numFound": 0},
    }
    assert SearchResponse.from_solr_result(solr_result, "", "", time=0.1).partial_results is False
