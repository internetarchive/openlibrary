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
    # DDCs
    "DDC: simple": ("ddc:65.8", "ddc:065.8"),
    "DDC: integer, no padding needed": ("ddc:658", "ddc:658"),
    "DDC: range": ("ddc:[61 TO 65]", "ddc:[061 TO 065]"),
    "DDC: range, open end": ("ddc:[23.23 TO *]", "ddc:[023.23 TO *]"),
    "DDC: wildcard": ("ddc:23.45*", "ddc:023.45*"),
    "DDC: wildcard integer": ("ddc:2*", "ddc:2*"),
    "DDC: ddc_sort": ("ddc_sort:65.8", "ddc_sort:065.8"),
    "DDC: quotes preserved": ('ddc:"65.8"', 'ddc:"065.8"'),
    # ebook_unavailable
    "ebook_unavailable: true": ("ebook_unavailable:true", "ebook_unavailable:1"),
    "ebook_unavailable: case-insensitive": ("ebook_unavailable:TRUE", "ebook_unavailable:1"),
    "ebook_unavailable: false negates, since absent is available": ("ebook_unavailable:false", "-ebook_unavailable:1"),
    "ebook_unavailable: 0 is false": ("ebook_unavailable:0", "-ebook_unavailable:1"),
    "ebook_unavailable: negated false is true": ("-ebook_unavailable:false", "ebook_unavailable:1"),
    "ebook_unavailable: inside a larger query": ("harry potter ebook_unavailable:false", "harry potter -ebook_unavailable:1"),
    "ebook_unavailable: edition prefix": ("edition.ebook_unavailable:true", "edition.ebook_unavailable:1"),
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


EBOOK_UNAVAILABLE_TESTS = {
    "ebook_unavailable:true": ("*:*", "+ebook_unavailable:1"),
    "ebook_unavailable:false": ("*:*", "-ebook_unavailable:1"),
    "ebook_access:borrowable ebook_unavailable:false": ("ebook_access:borrowable ", "+ebook_access:borrowable -ebook_unavailable:1"),
}


@pytest.mark.parametrize(("query", "queries"), EBOOK_UNAVAILABLE_TESTS.items())
def test_q_to_solr_params_ebook_unavailable_is_edition_only(query, queries):
    """Work docs don't carry ebook_unavailable, so it only filters the editions."""
    web.ctx.lang = "en"
    s = WorkSearchScheme()
    with patch("openlibrary.plugins.worksearch.schemes.works.convert_iso_to_marc", return_value="eng"):
        params = dict(s.q_to_solr_params(s.process_user_query(query), {"editions:[subquery]"}, []))
    assert (params["userWorkQuery"], params["userEdQuery"]) == queries


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
