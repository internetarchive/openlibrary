from unittest.mock import patch

import web

from openlibrary.plugins.worksearch.code import (
    _prepare_solr_query_params,
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
