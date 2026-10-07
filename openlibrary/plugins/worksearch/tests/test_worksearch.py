from unittest.mock import patch

import pytest
import web

from openlibrary.plugins.worksearch import code
from openlibrary.plugins.worksearch.code import (
    DidYouMean,
    SearchResponse,
    _get_readable_count,
    _prepare_solr_query_params,
    _primary_correction,
    build_corrected_query,
    did_you_mean_link,
    did_you_mean_search_url,
    find_did_you_mean_async,
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
            "cover_width": 301,
            "cover_height": 500,
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
            "cover_width": 301,
            "cover_height": 500,
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


def _spellcheck_q(param: dict) -> str | None:
    """Return the `spellcheck.q` param OL would send for `param`, if any."""
    params, _ = _prepare_solr_query_params(WorkSearchScheme(), param)
    values = [v for k, v in params if k == "spellcheck.q"]
    assert len(values) <= 1, "spellcheck.q must not be sent more than once"
    return values[0] if values else None


def test_prepare_solr_query_params_spellcheck_q_is_raw_user_query():
    """The spellchecker must be handed the raw free-text query.

    SpellCheckComponent falls back to parsing the raw `q` request param when
    `spellcheck.q` is absent, and OL's `q` is an edismax local-param wrapper
    full of OL's own field names. Spellchecking that produced corrections for
    `lccn`, `chapter`, `subject`, ... rather than anything the user typed."""
    assert _spellcheck_q({"q": "harry potter"}) == "harry potter"
    # Raw, i.e. not the luqum-processed/escaped form OL builds `q` from.
    assert _spellcheck_q({"q": "the hobbit's tale"}) == "the hobbit's tale"


def test_prepare_solr_query_params_spellcheck_q_excludes_structured_terms():
    """`spellcheck.q` must carry only the free-text part, never `userWorkQuery`.

    `userWorkQuery` merges free text with structured clauses, so reusing it
    would feed `author_name` / `author_alternative_name` back in as
    spellcheck candidates -- the same class of bug as spellchecking `q`."""
    params, _ = _prepare_solr_query_params(WorkSearchScheme(), {"q": "tolkien ring", "author": "J. R. R."})
    d = dict(params)
    assert d["spellcheck.q"] == "tolkien ring"
    # The structured terms are still in the search query, just not spellchecked.
    assert "author_name" in d["userWorkQuery"]
    assert "author_name" not in d["spellcheck.q"]


def test_prepare_solr_query_params_no_spellcheck_q_without_free_text():
    """Searches with no free-text query (author/isbn/subject browse) must not
    ask for spellchecking at all. With no `spellcheck.q` to send, the checker
    would fall back to the edismax wrapper in `q` and "correct" OL's field
    names on every browse."""
    scheme = WorkSearchScheme()
    assert _spellcheck_q({"author": "Tolkien"}) is None
    assert _spellcheck_q({"isbn": "9780261102217"}) is None
    assert _spellcheck_q({}) is None
    for param in ({"author": "Tolkien"}, {"isbn": "9780261102217"}, {}):
        params, _ = _prepare_solr_query_params(scheme, param)
        assert not [k for k, _ in params if k.startswith("spellcheck")]


def test_prepare_solr_query_params_normal_q_unchanged_by_spellcheck_q():
    """Adding spellcheck.q must not perturb the actual search: `q` stays the
    edismax wrapper and `userWorkQuery` still carries the processed text."""
    params, _ = _prepare_solr_query_params(WorkSearchScheme(), {"q": "harry potter"})
    d = dict(params)
    assert "{!edismax" in d["q"]
    assert d["userWorkQuery"] == "harry potter"
    # Spellcheck is requested as before, plus the new spellcheck.q.
    assert d["spellcheck"] == "true"
    assert d["spellcheck.count"] == 10
    assert d["spellcheck.q"] == "harry potter"


def _solr_result(**extra) -> dict:
    """A minimal but realistic Solr /select payload, with optional extras merged in."""
    result = {
        "responseHeader": {"status": 0, "QTime": 3},
        "response": {
            "numFound": 2,
            "start": 0,
            "numFoundExact": True,
            "docs": [
                {"key": "/works/OL1W", "title": "Test Book", "edition_count": 3},
                {"key": "/works/OL2W", "title": "Other Book", "edition_count": 1},
            ],
        },
        "highlighting": {"OL1W": {"title": ["<em>Test</em> Book"]}},
        # Solr returns facet_fields as a flat [val, count, ...] array. A neutral
        # field is used so this stays independent of get_language_name/req_context.
        "facet_counts": {"facet_fields": {"subject": ["science", 2]}},
    }
    result.update(extra)
    return result


def _response(**extra) -> SearchResponse:
    """Parse `_solr_result(**extra)` through the real from_solr_result entry point."""
    return SearchResponse.from_solr_result(_solr_result(**extra), sort="", solr_select="/select", time=0.01)


def test_spellcheck_absent_leaves_response_untouched():
    """A Solr response with no `spellcheck` section must behave exactly as before.

    Every pre-existing field is asserted here, so the Phase 2 addition cannot
    quietly change what callers read."""
    result = _response()
    assert result.spellcheck is None

    # Pre-existing fields are unchanged.
    assert result.num_found == 2
    assert result.num_found_exact is True
    assert len(result.docs) == 2
    assert result.docs[0]["title"] == "Test Book"
    assert result.sort == ""
    assert result.spellcheck is None
    assert result.highlighting == {"OL1W": {"title": ["<em>Test</em> Book"]}}
    assert result.facet_counts == {"subject": [("science", "science", 2)]}
    assert result.error is None
    assert result.time == 0.01
    # raw_resp keeps the whole Solr payload, spellcheck section included.
    assert result.raw_resp == _solr_result()


def test_spellcheck_suggestion_is_preserved():
    """A single correction is preserved, including the token it corrects.

    This is the flat shape Solr sends by default, as captured from a live
    OL-shaped Solr index in Phase 1.
    """
    result = _response(
        spellcheck={
            "suggestions": [
                "Nitrogenn",
                {
                    "numFound": 2,
                    "startOffset": 0,
                    "endOffset": 9,
                    "suggestion": [
                        {"word": "nitrogen", "freq": 1234},
                        {"word": "nitrogenio", "freq": 12},
                    ],
                },
            ]
        }
    )
    assert result.spellcheck is not None
    (suggestion,) = result.spellcheck.suggestions
    assert suggestion.original_token == "Nitrogenn"
    assert suggestion.suggestions == ["nitrogen", "nitrogenio"]
    assert suggestion.start_offset == 0
    assert suggestion.end_offset == 9
    # Nothing else about the search moved.
    assert result.num_found == 2
    assert len(result.docs) == 2


def test_spellcheck_multiple_suggestions_are_not_lost():
    """Several misspelled tokens and several corrections each are all kept.

    Also covers Solr's `extendedResults` shape, where corrections arrive as
    `{'word': ..., 'freq': ...}` objects with an explicit `originalToken`.
    """
    result = _response(
        spellcheck={
            "correctlySpelled": False,
            "suggestions": [
                "telivision",
                {
                    "originalToken": "telivision",
                    "startOffset": 0,
                    "endOffset": 10,
                    "origFreq": 7,
                    "suggestion": [
                        {"word": "television", "freq": 310},
                        {"word": "televise", "freq": 22},
                    ],
                },
                "bibliograpy",
                {
                    "originalToken": "bibliograpy",
                    "startOffset": 11,
                    "endOffset": 22,
                    "origFreq": 2,
                    "suggestion": [{"word": "bibliography", "freq": 88}],
                },
            ],
        }
    )
    spellcheck = result.spellcheck
    assert spellcheck is not None
    assert [s.original_token for s in spellcheck.suggestions] == ["telivision", "bibliograpy"]
    assert spellcheck.suggestions[0].suggestions == ["television", "televise"]
    assert spellcheck.suggestions[0].original_freq == 7
    assert spellcheck.suggestions[1].suggestions == ["bibliography"]
    assert spellcheck.suggestions[1].start_offset == 11
    assert spellcheck.correctly_spelled is False
    # The untouched payload is retained, so nothing is lost by parsing.
    assert spellcheck.raw["suggestions"][0] == "telivision"


def test_spellcheck_no_suggestions_creates_no_dym_state():
    """An empty spellcheck section must not look like a did-you-mean opportunity."""
    assert _response(spellcheck={"suggestions": []}).spellcheck is None
    assert _response(spellcheck={}).spellcheck is None
    assert _response(spellcheck={"correctlySpelled": True, "suggestions": []}).spellcheck is None
    # Results are still served normally.
    assert _response(spellcheck={"suggestions": []}).num_found == 2


def test_spellcheck_collations_are_preserved_when_present():
    """Collation data is parsed even though OL sets `spellcheck.collate=false`.

    If that config ever flips, the data still reaches the next phase.
    """
    result = _response(
        spellcheck={
            "suggestions": ["telivision", {"suggestion": [{"word": "television", "freq": 1}]}],
            "collations": [
                "television",
                {
                    "collationQuery": "television",
                    "hits": 5,
                    "misspellingsAndCorrections": [["telivision", "television"]],
                },
            ],
        }
    )
    (collation,) = result.spellcheck.collations
    assert collation.collation_query == "television"
    assert collation.hits == 5
    assert collation.misspellings_and_corrections == [["telivision", "television"]]


def test_spellcheck_does_not_change_search_result_set():
    """The central Phase 2 guarantee: the docs Solr returned are identical
    whether or not a spellcheck section rides along."""
    without = _response()
    with_spellcheck = _response(spellcheck={"suggestions": ["harry", {"suggestion": [{"word": "harry", "freq": 1}]}]})
    assert without.docs == with_spellcheck.docs
    assert without.num_found == with_spellcheck.num_found
    assert without.num_found_exact == with_spellcheck.num_found_exact
    assert without.highlighting == with_spellcheck.highlighting
    assert without.facet_counts == with_spellcheck.facet_counts
    # Only the parsed spellcheck data differs.
    assert with_spellcheck.spellcheck is not None
    assert without.spellcheck is None


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


def _stub_search_web_input(monkeypatch):
    """search.GET() makes two web.input() calls: one just for q/q2, then the
    real one with a q="hello" query and no other params set."""

    def fake_input(**defaults):
        if "q2" in defaults:
            return web.storage(q="", q2="")
        values = dict(defaults)
        values["q"] = "hello"
        return web.storage(**values)

    monkeypatch.setattr(code.web, "input", fake_input)


class TestSearchAvailabilityPreparedInPython:
    """Regression coverage for openlibrary#13419 subtask 5: work_search.html
    used to call add_availability() itself, mid-render, for every search
    results page -- an outbound network call from template rendering (the
    same class of bug the LoanStatus groundtruth fallback removal fixes for
    /works and /books). search.GET() must batch-augment availability in
    Python before the template renders, and hand the template an
    already-prepared `works` list instead of the raw `get_doc` function."""

    def test_add_availability_runs_in_python_before_render_with_prepared_works(self, monkeypatch):
        _stub_search_web_input(monkeypatch)
        solr_doc = {
            "key": "/works/OL1W",
            "title": "Test Book",
            "edition_count": 1,
            "ia": ["testbook"],
        }
        search_response = SearchResponse(facet_counts={}, sort="", docs=[solr_doc], num_found=0, solr_select="")

        call_order = []
        render_calls = []

        def fake_add_availability(items):
            call_order.append("add_availability")
            return items

        def fake_render_work_search(*a, **kw):
            call_order.append("render")
            render_calls.append(a)
            return "rendered"

        def run():
            with (
                patch.object(code, "run_solr_query", return_value=search_response),
                patch.object(code, "add_availability", side_effect=fake_add_availability) as mock_add_availability,
            ):
                monkeypatch.setattr(code.render, "work_search", fake_render_work_search, raising=False)
                return code.search().GET(), mock_add_availability

        result, mock_add_availability = _with_req_context(run)

        assert result == "rendered"
        # add_availability ran exactly once, before render.work_search --
        # not per-item inside the template's own render pass.
        assert call_order == ["add_availability", "render"]
        mock_add_availability.assert_called_once()

        (availability_items,) = mock_add_availability.call_args[0]
        assert len(availability_items) == 1
        assert availability_items[0]["key"] == "/works/OL1W"

        # work_search.html no longer takes the raw `get_doc` function as its
        # 3rd positional arg -- it takes the already-get_doc()-mapped,
        # already-availability-augmented `works` list.
        (render_args,) = render_calls
        works_arg = render_args[2]
        assert works_arg == [get_doc(solr_doc)]
        assert works_arg is not get_doc


# ---------------------------------------------------------------------------
# Phase 3: did-you-mean candidate validation
# ---------------------------------------------------------------------------


def _spellcheck(payload: dict):
    """Parse a Solr spellcheck payload the way the pipeline would."""
    return SearchResponse.parse_spellcheck(payload)


_ONE_TYPO = {
    "suggestions": [
        "industril",
        {"startOffset": 0, "endOffset": 9, "suggestion": ["industrial"]},
    ]
}
_TWO_TYPOS = {
    "suggestions": [
        "competiton",
        {"startOffset": 0, "endOffset": 10, "suggestion": ["competition"]},
        "polciy",
        {"startOffset": 11, "endOffset": 17, "suggestion": ["policy"]},
    ]
}


def test_build_corrected_query_applies_every_correction():
    """One pass over the query fixes every misspelled token Solr flagged."""
    assert build_corrected_query("industril applications", _spellcheck(_ONE_TYPO)) == "industrial applications"
    assert build_corrected_query("competiton polciy", _spellcheck(_TWO_TYPOS)) == "competition policy"


def test_build_corrected_query_without_offsets_replaces_whole_words_only():
    """With no offsets Solr reported, fall back to a word-boundary replacement.

    Substring matches must survive: correcting `cat` may not wreck `concatenate`.
    """
    sc = _spellcheck({"suggestions": ["cat", {"suggestion": ["cart"]}]})
    assert build_corrected_query("concatenate cat catalogue", sc) == "concatenate cart catalogue"


def test_build_corrected_query_returns_none_when_nothing_to_do():
    """Never return the query unchanged -- that would look like a usable suggestion."""
    assert build_corrected_query("harry potter", None) is None
    assert build_corrected_query("harry potter", _spellcheck({"suggestions": []})) is None
    assert build_corrected_query("", _spellcheck(_ONE_TYPO)) is None
    # A "correction" identical to the original token is not a correction.
    same = _spellcheck({"suggestions": ["potter", {"startOffset": 6, "endOffset": 12, "suggestion": ["potter"]}]})
    assert build_corrected_query("harry potter", same) is None


def test_primary_correction_is_solrs_top_ranked():
    sc = _spellcheck(_TWO_TYPOS)
    assert _primary_correction(sc) == ("competiton", "competition")
    assert _primary_correction(_spellcheck({"suggestions": []})) is None


class _StubSolr:
    """Captures the validation query and returns a fixed result count."""

    def __init__(self, num_found: int):
        self.num_found = num_found
        self.calls: list[dict] = []

    async def __call__(self, scheme, param=None, **kwargs):
        self.calls.append({"scheme": scheme, "param": dict(param or {}), **kwargs})
        return SearchResponse(facet_counts=None, sort="", docs=[], num_found=self.num_found, solr_select="/select")


async def _run_dym(param, spellcheck, num_found, main_num_found=0):
    """Run the did-you-mean decision.

    `num_found` is what the *validation* query finds; `main_num_found` is what the
    original search found, i.e. the Phase 5 zero-result gate. It defaults to 0 because
    every candidate that reaches validation is, by that gate, a zero-result search.
    """
    stub = _StubSolr(num_found)
    with patch.object(code, "run_solr_query_async", stub):
        return await find_did_you_mean_async(param, spellcheck, main_num_found), stub


@pytest.mark.asyncio
async def test_dym_no_spellcheck_data_never_validates():
    """No spellcheck section -> no candidate, and crucially no extra Solr query."""
    dym, stub = await _run_dym({"q": "industril applications"}, None, 99)
    assert dym is None
    assert stub.calls == []


@pytest.mark.asyncio
async def test_dym_correct_query_never_becomes_a_candidate():
    """A correctly-spelled query yields Solr's empty suggestion list, not a DYM."""
    dym, stub = await _run_dym({"q": "competition policy"}, _spellcheck({"suggestions": []}), 99)
    assert dym is None
    assert stub.calls == []


@pytest.mark.asyncio
async def test_dym_candidate_with_results_is_accepted():
    """A corrected query that matches documents is a proven-safe candidate."""
    param = {"q": "industril applications"}
    dym, stub = await _run_dym(param, _spellcheck(_ONE_TYPO), 2888)

    assert dym is not None
    assert dym.original_query == "industril applications"
    assert dym.corrected_query == "industrial applications"
    assert dym.original_token == "industril"
    assert dym.suggestion == "industrial"
    assert dym.num_found == 2888

    # Validation must be a cheap count that cannot recurse into the spellchecker.
    (call,) = stub.calls
    assert call["rows"] == 0
    assert call["spellcheck_count"] == 0
    assert call["facet"] is False
    assert call["request_label"] == "BOOK_SEARCH_DID_YOU_MEAN"
    # "editions" keeps the edition block-join, so the count matches real results.
    assert "editions" in call["fields"]


@pytest.mark.asyncio
async def test_dym_candidate_with_zero_results_is_rejected():
    """A correction that matches nothing must not be offered."""
    dym, _ = await _run_dym({"q": "industril applications"}, _spellcheck(_ONE_TYPO), 0)
    assert dym is None


@pytest.mark.asyncio
async def test_dym_preserves_filters_and_structured_terms():
    """Validation must re-run under the user's own filters and structured terms.

    A correction that finds books, but none the user can actually see because of
    their filters, is not a safe suggestion.
    """
    param = {
        "q": "competiton polciy",
        "language": ["eng", "spa"],
        "author": "Tolkien",
        "has_fulltext": "true",
    }
    original = dict(param)
    dym, stub = await _run_dym(param, _spellcheck(_TWO_TYPOS), 12)

    assert dym is not None
    assert dym.corrected_query == "competition policy"
    (call,) = stub.calls
    assert call["param"]["q"] == "competition policy"
    assert call["param"]["language"] == ["eng", "spa"]
    assert call["param"]["author"] == "Tolkien"
    assert call["param"]["has_fulltext"] == "true"
    # The caller's params must not be mutated.
    assert param == original


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "param",
    [
        {"author": "Tolkien"},
        {"isbn": "9780261102217"},
        {"subject": "science"},
        {},
    ],
    ids=["author", "isbn", "subject", "empty"],
)
async def test_dym_structured_only_searches_are_never_candidates(param):
    """author/isbn/subject browse has no free text to correct, so never a candidate.

    It must not even reach Solr: Phase 1 already stopped asking for spellcheck on
    these, and validation must not undo that by issuing its own query.
    """
    dym, stub = await _run_dym(param, _spellcheck(_ONE_TYPO), 500)
    assert dym is None
    assert stub.calls == []


@pytest.mark.asyncio
async def test_dym_rejected_candidate_leaves_the_search_response_untouched():
    """The central Phase 3 guarantee.

    When no valid candidate exists the search must be exactly what it was before
    did-you-mean existed: same params, same parsed response.
    """
    param = {"q": "industril applications", "language": "eng"}
    solr = _solr_result()
    solr["spellcheck"] = _ONE_TYPO
    response = SearchResponse.from_solr_result(solr, sort="", solr_select="/select", time=0.01)

    before_docs = response.docs
    before_num_found = response.num_found
    before_params = dict(param)

    # A correction that matches nothing -> rejected.
    dym, _ = await _run_dym(param, response.spellcheck, 0)
    assert dym is None

    # Nothing about the search moved.
    assert response.docs is before_docs
    assert response.docs == before_docs
    assert response.num_found == before_num_found
    assert param == before_params
    # The spellcheck data itself is still there for a later phase to use.
    assert response.spellcheck is not None
    assert response.spellcheck.suggestions[0].original_token == "industril"


# ---------------------------------------------------------------------------
# Phase 5: the zero-result gate, and /search integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dym_gate_skips_validation_when_the_search_found_results():
    """Phase 5's central rule: a did-you-mean is only considered at zero results.

    The gate must be decided *before* any Solr work, so a populated search page pays
    nothing -- no correction lookup, no rows=0 validation query.
    """
    dym, stub = await _run_dym({"q": "industril applications"}, _spellcheck(_ONE_TYPO), 2888, main_num_found=42)

    assert dym is None
    # No validation query was issued at all, even though one would have matched.
    assert stub.calls == []


@pytest.mark.asyncio
async def test_dym_gate_treats_a_missing_result_count_as_no_candidate():
    """An errored search reports num_found=None; it must not become a candidate."""
    dym, stub = await _run_dym({"q": "industril applications"}, _spellcheck(_ONE_TYPO), 2888, main_num_found=None)

    assert dym is None
    assert stub.calls == []


@pytest.mark.asyncio
async def test_dym_gate_lets_a_zero_result_search_through():
    """The gate must not swallow the case it exists for."""
    dym, stub = await _run_dym({"q": "industril applications"}, _spellcheck(_ONE_TYPO), 2888, main_num_found=0)

    assert dym is not None
    assert dym.corrected_query == "industrial applications"
    assert len(stub.calls) == 1


def _a_dym(param=None):
    return DidYouMean(
        original_query="industril applications",
        corrected_query="industrial applications",
        original_token="industril",
        suggestion="industrial",
        num_found=2888,
    )


def test_did_you_mean_search_url_keeps_the_users_filters():
    """Following the suggestion must not silently drop the user's own filters."""
    param = {"q": "industril applications", "language": ["eng", "spa"], "sort": "old", "page": ""}

    url = did_you_mean_search_url(_a_dym(), param)

    assert url.startswith("/search?")
    assert "q=industrial+applications" in url
    assert "language=eng" in url
    assert "language=spa" in url
    assert "sort=old" in url
    # Empty params carry no meaning and are dropped rather than sent as "?page=".
    assert "page=" not in url
    # The user's misspelling is not left behind in the URL.
    assert "industril" not in url


def test_did_you_mean_link_escapes_the_corrected_query():
    """The corrected query is derived from user input and lands in raw template output.

    Templetor's `$:_()` does not escape, so did_you_mean_link owns escaping both halves.
    """
    dym = DidYouMean(
        original_query="<script>alert(1)</script>",
        corrected_query='<script>alert("xss")</script>',
        original_token="script",
        suggestion="scripts",
        num_found=3,
    )

    link = did_you_mean_link(dym, {"q": dym.original_query})

    assert "<script>" not in link
    assert "&lt;script&gt;" in link
    assert 'href="/search?q=%3Cscript%3E' in link


def _run_search_page(monkeypatch, *, q, num_found, spellcheck, dym):
    """Drive search.GET() and return what render.work_search was handed."""
    render_kwargs = {}

    def fake_input(**defaults):
        if "q2" in defaults:
            return web.storage(q="", q2="")
        values = dict(defaults)
        values["q"] = q
        return web.storage(**values)

    monkeypatch.setattr(code.web, "input", fake_input)

    search_response = SearchResponse(
        facet_counts={},
        sort="",
        docs=[],
        num_found=num_found,
        solr_select="",
        spellcheck=spellcheck,
    )

    def fake_render_work_search(*a, **kw):
        render_kwargs.update(kw)
        return "rendered"

    def run():
        with (
            patch.object(code, "run_solr_query", return_value=search_response),
            patch.object(code, "add_availability", return_value=[]),
            patch.object(code, "find_did_you_mean", return_value=dym) as mock_dym,
        ):
            monkeypatch.setattr(code.render, "work_search", fake_render_work_search, raising=False)
            result = code.search().GET()
            return result, mock_dym

    result, mock_dym = _with_req_context(run)
    return result, render_kwargs, mock_dym


def test_search_offers_a_did_you_mean_on_a_zero_result_search(monkeypatch):
    """The wiring: /search asks for a candidate only because it found nothing."""
    dym = _a_dym()
    result, render_kwargs, mock_dym = _run_search_page(
        monkeypatch,
        q="industril applications",
        num_found=0,
        spellcheck=_spellcheck(_ONE_TYPO),
        dym=dym,
    )

    assert result == "rendered"
    # The search's own num_found is what gates the decision, so it must be passed.
    assert mock_dym.call_args.args[2] == 0
    assert render_kwargs["did_you_mean"] is dym


def test_search_offers_no_did_you_mean_when_it_found_results(monkeypatch):
    """A populated results page must render exactly as it did before Phase 5."""
    _, render_kwargs, _ = _run_search_page(
        monkeypatch,
        q="industril applications",
        num_found=17,
        spellcheck=_spellcheck(_ONE_TYPO),
        dym=None,
    )

    assert render_kwargs["did_you_mean"] is None


def test_search_offers_no_did_you_mean_without_a_correction(monkeypatch):
    """Zero results but nothing to suggest -> the page is untouched."""
    _, render_kwargs, _ = _run_search_page(
        monkeypatch,
        q="industril applications",
        num_found=0,
        spellcheck=_spellcheck({"suggestions": []}),
        dym=None,
    )

    assert render_kwargs["did_you_mean"] is None
