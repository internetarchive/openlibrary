from unittest.mock import patch

import pytest
import web

from openlibrary.plugins.worksearch.schemes.works import WorkSearchScheme

pytestmark = pytest.mark.usefixtures("request_context_fixture")


# {'Test name': ('query', fields[])}
QUERY_PARSER_TESTS = {
    "No fields": ("query here", "query here"),
    "Misc": (
        "title:(Holidays are Hell) authors:(Kim Harrison) OR authors:(Lynsay Sands)",
        "alternative_title:(Holidays are Hell) author_name:(Kim Harrison) OR author_name:(Lynsay Sands)",
    ),
    "Author field": (
        "food rules author:pollan",
        "food rules author_name:pollan",
    ),
    "Invalid dashes": (
        "foo foo bar -",
        "foo foo bar \\-",
    ),
    "Field aliases": (
        "title:food rules by:pollan",
        "alternative_title:(food rules) author_name:pollan",
    ),
    "Fields are case-insensitive aliases": (
        "food rules By:pollan",
        "food rules author_name:pollan",
    ),
    "Spaces after fields": (
        'title: "Harry Potter"',
        'alternative_title:"Harry Potter"',
    ),
    "Quotes": (
        'title:"food rules" author:pollan',
        'alternative_title:"food rules" author_name:pollan',
    ),
    "Unmatched double-quote": (
        'title:Compilation Group for the "History of Modern China',
        'title\\:Compilation Group for the \\"History of Modern China',
    ),
    "Leading text": (
        "query here title:food rules author:pollan",
        "query here alternative_title:(food rules) author_name:pollan",
    ),
    "Colons in query": (
        "flatland:a romance of many dimensions",
        "flatland\\:a romance of many dimensions",
    ),
    "Spaced colons in query": (
        "flatland : a romance of many dimensions",
        "flatland\\: a romance of many dimensions",
    ),
    "Colons in field": (
        "title:flatland:a romance of many dimensions",
        "alternative_title:(flatland\\:a romance of many dimensions)",
    ),
    "Operators": (
        "authors:Kim Harrison OR authors:Lynsay Sands",
        "author_name:(Kim Harrison) OR author_name:(Lynsay Sands)",
    ),
    "ISBN-like": (
        "978-0-06-093546-7",
        "isbn:(9780060935467)",
    ),
    "Normalizes ISBN": (
        "isbn:978-0-06-093546-7",
        "isbn:9780060935467",
    ),
    "Does not normalize ISBN stars": (
        "isbn:979*",
        "isbn:979*",
    ),
    # LCCs
    "LCC: quotes added if space present": (
        "lcc:NC760 .B2813 2004",
        'lcc:"NC-0760.00000000.B2813 2004"',
    ),
    "LCC: star added if no space": (
        "lcc:NC760 .B2813",
        "lcc:NC-0760.00000000.B2813*",
    ),
    "LCC: Noise left as is": (
        "lcc:good evening",
        "lcc:(good evening)",
    ),
    "LCC: range": (
        "lcc:[NC1 TO NC1000]",
        "lcc:[NC-0001.00000000 TO NC-1000.00000000]",
    ),
    "LCC: prefix": (
        "lcc:NC76.B2813*",
        "lcc:NC-0076.00000000.B2813*",
    ),
    "LCC: suffix": (
        "lcc:*B2813",
        "lcc:*B2813",
    ),
    "LCC: multi-star without prefix": (
        "lcc:*B2813*",
        "lcc:*B2813*",
    ),
    "LCC: multi-star with prefix": (
        "lcc:NC76*B2813*",
        "lcc:NC-0076*B2813*",
    ),
    "LCC: quotes preserved": (
        'lcc:"NC760 .B2813"',
        'lcc:"NC-0760.00000000.B2813"',
    ),
    # TODO Add tests for DDC
    # more-like-this
    "like: is a search field, not escaped text": (
        "like:OL123W",
        "like:OL123W",
    ),
    "like: keeps a full work key (with / escaped)": (
        "like:/works/OL123W",
        "like:\\/works\\/OL123W",
    ),
}


@pytest.mark.parametrize(
    ("query", "parsed_query"),
    QUERY_PARSER_TESTS.values(),
    ids=QUERY_PARSER_TESTS.keys(),
)
def test_process_user_query(query, parsed_query):
    s = WorkSearchScheme()
    assert s.process_user_query(query) == parsed_query


EDITION_KEY_TESTS = {
    "edition_key:OL123M": '+key:"/books/OL123M"',
    'edition_key:"OL123M"': '+key:"/books/OL123M"',
    'edition_key:"/books/OL123M"': '+key:"/books/OL123M"',
    "edition_key:(OL123M)": '+key:("/books/OL123M")',
    "edition_key:(OL123M OR OL456M)": '+key:("/books/OL123M" OR "/books/OL456M")',
}


@pytest.mark.parametrize(("query", "edQuery"), EDITION_KEY_TESTS.items())
def test_q_to_solr_params_edition_key(query, edQuery):
    web.ctx.lang = "en"
    s = WorkSearchScheme()

    with patch("openlibrary.plugins.worksearch.schemes.works.convert_iso_to_marc") as mock_fn:
        mock_fn.return_value = "eng"
        params = s.q_to_solr_params(query, {"editions:[subquery]"}, [])
    params_d = dict(params)
    assert params_d["userWorkQuery"] == query
    assert params_d["userEdQuery"] == edQuery


def test_cover_dimensions_fetched_for_works_and_editions():
    """Cover dimensions must reach both the work `fl` and the editions subquery,
    since the search result macro reads them off the selected edition."""
    web.ctx.lang = "en"
    s = WorkSearchScheme()
    assert {"cover_width", "cover_height"} <= s.default_fetched_fields

    solr_fields = (s.default_fetched_fields | {"editions:[subquery]"}) - {"editions"}
    with patch("openlibrary.plugins.worksearch.schemes.works.convert_iso_to_marc") as mock_fn:
        mock_fn.return_value = "eng"
        params = s.q_to_solr_params("harry potter", solr_fields, [])
    editions_fl = dict(params)["editions.fl"].split(",")
    assert "cover_width" in editions_fl
    assert "cover_height" in editions_fl


def test_q_to_solr_params_local_params_fq_not_rewritten_for_editions():
    """A local-params fq (e.g. {!terms f=key}...) isn't a field:value facet filter and shouldn't be parsed as one for the editions subquery."""
    web.ctx.lang = "en"
    s = WorkSearchScheme()

    with patch("openlibrary.plugins.worksearch.schemes.works.convert_iso_to_marc") as mock_fn:
        mock_fn.return_value = "eng"
        params = s.q_to_solr_params(
            "*:*",
            {"editions:[subquery]"},
            [("fq", "{!terms f=key}/works/OL192489W")],
        )
    editions_fq_values = [v for k, v in params if k == "editions.fq"]
    assert not any("OL192489W" in v for v in editions_fq_values)


MLT_SEED_TESTS = {
    "Bare OLID": ("like:OL123W", ["/works/OL123W"]),
    "Full work key": ("like:/works/OL123W", ["/works/OL123W"]),
    "Quoted work key": ('like:"/works/OL123W"', ["/works/OL123W"]),
    "Lowercase OLID": ("like:ol123w", ["/works/OL123W"]),
    "Alongside another field": ("like:OL123W language:eng", ["/works/OL123W"]),
    "Several seeds": ("like:(OL1W OR OL2W)", ["/works/OL1W", "/works/OL2W"]),
    "Value naming no work": ("like:nonsense", []),
    "No like clause": ("language:eng", []),
}


@pytest.mark.parametrize(
    ("query", "seed_keys"),
    MLT_SEED_TESTS.values(),
    ids=MLT_SEED_TESTS.keys(),
)
def test_q_to_solr_params_mlt_seeds(query, seed_keys):
    web.ctx.lang = "en"
    s = WorkSearchScheme()

    with patch("openlibrary.plugins.worksearch.schemes.works.convert_iso_to_marc") as mock_fn:
        mock_fn.return_value = "eng"
        params = s.q_to_solr_params(s.process_user_query(query), {"editions:[subquery]"}, [])

    assert [v for k, v in params if k.startswith("mltSeed")] == seed_keys


def test_q_to_solr_params_mlt_query_shape():
    """A `like:` clause becomes a separate mandatory more-like-this clause, and
    drops out of the work/edition queries, which can't express local params."""
    web.ctx.lang = "en"
    s = WorkSearchScheme()

    with patch("openlibrary.plugins.worksearch.schemes.works.convert_iso_to_marc") as mock_fn:
        mock_fn.return_value = "eng"
        params = s.q_to_solr_params(s.process_user_query("like:OL123W subject:Zen"), {"editions:[subquery]"}, [])
    params_d = dict(params)

    assert params_d["mltSeed0"] == "/works/OL123W"
    assert "like" not in params_d["userWorkQuery"]
    assert params_d["userWorkQuery"] == "subject:Zen"
    assert "like" not in params_d["userEdQuery"]
    assert "{!mlt" in params_d["q"]
    # Solr's mlt parser only drops its own seed, so the seed is excluded explicitly
    assert '-key:("/works/OL123W")' in params_d["q"]


def test_q_to_solr_params_mlt_excludes_every_seed():
    web.ctx.lang = "en"
    s = WorkSearchScheme()

    with patch("openlibrary.plugins.worksearch.schemes.works.convert_iso_to_marc") as mock_fn:
        mock_fn.return_value = "eng"
        params = s.q_to_solr_params(s.process_user_query("like:(OL1W OR OL2W)"), {"editions:[subquery]"}, [])
    params_d = dict(params)

    assert '-key:("/works/OL1W" OR "/works/OL2W")' in params_d["q"]


def test_q_to_solr_params_mlt_only_query_matches_all_works():
    """`like:X` on its own leaves no user query, so the work query must not be
    left empty; the more-like-this clause does the filtering."""
    web.ctx.lang = "en"
    s = WorkSearchScheme()

    with patch("openlibrary.plugins.worksearch.schemes.works.convert_iso_to_marc") as mock_fn:
        mock_fn.return_value = "eng"
        params = s.q_to_solr_params(s.process_user_query("like:OL123W"), {"editions:[subquery]"}, [])
    params_d = dict(params)

    assert params_d["userWorkQuery"] == "*:*"
    assert "{!mlt" in params_d["q"]


def test_q_to_solr_params_invalid_like_matches_nothing():
    """`like:` is reachable from any search box, so a value that names no work
    has to produce no results rather than an error."""
    web.ctx.lang = "en"
    s = WorkSearchScheme()

    with patch("openlibrary.plugins.worksearch.schemes.works.convert_iso_to_marc") as mock_fn:
        mock_fn.return_value = "eng"
        params = s.q_to_solr_params(s.process_user_query("like:nonsense"), {"editions:[subquery]"}, [])
    params_d = dict(params)

    assert not any(k.startswith("mltSeed") for k, _ in params)
    assert "{!mlt" not in params_d["q"]
    assert "(*:* -*:*)" in params_d["q"]


def test_q_to_solr_params_no_mlt_clause_when_no_like():
    """Queries without `like:` must be untouched by the more-like-this handling."""
    web.ctx.lang = "en"
    s = WorkSearchScheme()

    with patch("openlibrary.plugins.worksearch.schemes.works.convert_iso_to_marc") as mock_fn:
        mock_fn.return_value = "eng"
        params = s.q_to_solr_params(s.process_user_query("subject:Zen"), {"editions:[subquery]"}, [])
    params_d = dict(params)

    assert not any(k.startswith("mltSeed") for k, _ in params)
    assert "{!mlt" not in params_d["q"]


def test_q_to_solr_params_mlt_params_overridable():
    """MLT tuning comes from the request so it can be A/B'd without a deploy."""
    from openlibrary.fastapi.models import SolrInternalsParams

    web.ctx.lang = "en"
    s = WorkSearchScheme()

    with patch("openlibrary.plugins.worksearch.schemes.works.convert_iso_to_marc") as mock_fn:
        mock_fn.return_value = "eng"
        params = s.q_to_solr_params(
            s.process_user_query("like:OL123W"),
            {"editions:[subquery]"},
            [],
            solr_internals_params=SolrInternalsParams(mlt_mintf="7", mlt_qf="subject"),
        )
    q = dict(params)["q"]

    assert "mintf=7" in q
    assert "qf=subject " in q
    # Unmentioned params keep their defaults
    assert "maxqt=50" in q


def test_q_to_solr_params_no_popularity_boost_for_mlt():
    """OL's popularity prior is additive with the more-like-this score and of
    comparable size, so leaving it on ranks by fame instead of likeness."""
    web.ctx.lang = "en"
    s = WorkSearchScheme()

    with patch("openlibrary.plugins.worksearch.schemes.works.convert_iso_to_marc") as mock_fn:
        mock_fn.return_value = "eng"
        mlt = dict(s.q_to_solr_params(s.process_user_query("like:OL123W"), {"editions:[subquery]"}, []))
        plain = dict(s.q_to_solr_params(s.process_user_query("dune"), {"editions:[subquery]"}, []))

    # Match the popularity function itself: the mlt clause has a `boost` local
    # param of its own, and the parent clause mentions edition_count.
    assert 'boost="sum(' not in mlt["q"]
    # Ordinary searches keep it
    assert 'boost="sum(' in plain["q"]


def test_q_to_solr_params_popularity_boost_still_overridable_for_mlt():
    """The A/B knob wins over our default, so a prior can be tried on top."""
    from openlibrary.fastapi.models import SolrInternalsParams

    web.ctx.lang = "en"
    s = WorkSearchScheme()

    with patch("openlibrary.plugins.worksearch.schemes.works.convert_iso_to_marc") as mock_fn:
        mock_fn.return_value = "eng"
        params = s.q_to_solr_params(
            s.process_user_query("like:OL123W"),
            {"editions:[subquery]"},
            [],
            solr_internals_params=SolrInternalsParams(solr_boost="log(readinglog_count)"),
        )

    assert 'boost="log(readinglog_count)"' in dict(params)["q"]
