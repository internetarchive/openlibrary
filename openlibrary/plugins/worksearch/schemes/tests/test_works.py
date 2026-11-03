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


# --- Sort validation (issue #13988): an unknown sort must raise a clear
# ValueError naming the valid options, NOT a bare KeyError (which surfaces to
# the user as an opaque 500). ---


@pytest.mark.parametrize(
    ("user_sort", "expected"),
    [
        ("editions", "edition_count desc"),
        ("new", "first_publish_year desc"),
        ("editions,new", "edition_count desc,first_publish_year desc"),
        ("editions, new", "edition_count desc,first_publish_year desc"),
        ("random", "random_1 asc"),
        ("random_custom_seed", "random_1_custom_seed asc"),
        # Carousels pass comma-separated compound sorts
        (
            "trending,trending_score_hourly_sum",
            "def(trending_z_score, 0) desc,def(trending_score_hourly_sum, 0) desc",
        ),
    ],
)
def test_process_user_sort_valid(user_sort, expected):
    assert WorkSearchScheme().process_user_sort(user_sort) == expected


@pytest.mark.parametrize(
    "user_sort",
    [
        "bogus",
        "title desc",  # 'title' is valid but 'title desc' is not a key
        "ranking",  # documented for subjects but never a real key
        "new,bogus",  # one good key, one bad -> still invalid
    ],
)
def test_process_user_sort_invalid_raises_value_error(user_sort):
    # Must be a ValueError (not the pre-fix KeyError), and must name the bad key.
    with pytest.raises(ValueError, match="Invalid sort option"):
        WorkSearchScheme().process_user_sort(user_sort)


@pytest.mark.parametrize(
    "user_sort",
    ["", "new", "editions,new", "random", "random_seed", "random.hourly", "random.daily_x"],
)
def test_validate_user_sort_accepts_valid(user_sort):
    assert WorkSearchScheme.validate_user_sort(user_sort) == user_sort


@pytest.mark.parametrize("user_sort", ["bogus", "title desc", "ranking", "new,bogus"])
def test_validate_user_sort_rejects_invalid(user_sort):
    with pytest.raises(ValueError, match="Invalid sort option"):
        WorkSearchScheme.validate_user_sort(user_sort)


# --- Empty/whitespace components (trailing/doubled commas, bare spaces) must
# resolve to "no sort" rather than 500 (`self.sorts[""]` KeyError). This asserts
# on process_user_sort directly — unmocked — because the FastAPI endpoint tests
# stub the Solr call and never reach process_user_sort. Regression for #13988. ---


@pytest.mark.parametrize(
    ("user_sort", "expected"),
    [
        ("editions,", "edition_count desc"),  # trailing comma
        (",new", "first_publish_year desc"),  # leading comma
        ("new,", "first_publish_year desc"),
        ("editions,,new", "edition_count desc,first_publish_year desc"),  # doubled comma
        ("editions, ,new", "edition_count desc,first_publish_year desc"),  # whitespace component
        (" ", ""),  # whitespace-only -> no sort
        ("", ""),  # empty -> no sort
    ],
)
def test_process_user_sort_skips_empty_components(user_sort, expected):
    # Must NOT raise KeyError; empty components are dropped.
    assert WorkSearchScheme().process_user_sort(user_sort) == expected


@pytest.mark.parametrize("user_sort", ["editions,", ",new", "editions,,new", " ", ""])
def test_validate_user_sort_allows_empty_components(user_sort):
    # validate_user_sort and process_user_sort MUST agree on empty components.
    assert WorkSearchScheme.validate_user_sort(user_sort) == user_sort
