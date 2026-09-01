from types import SimpleNamespace

import httpx
import pytest

from infogami import config
from openlibrary.core import fulltext
from openlibrary.utils import request_context


@pytest.mark.usefixtures("request_context_fixture")
class Test_fulltext_search_api:
    @pytest.mark.asyncio
    async def test_no_config(self):
        response = await fulltext.fulltext_search_api({})
        assert response == {"error": "Unable to prepare search engine"}

    @pytest.mark.asyncio
    async def test_query_exception(self, httpx_mock, monkeypatch):
        url = "http://mock"
        monkeypatch.setattr(config, "plugin_inside", {"search_endpoint": url}, raising=False)
        request = httpx.Request("GET", "http://mock")
        response = httpx.Response(500, request=request)
        error = httpx.HTTPStatusError("Unable to Connect", request=request, response=response)

        httpx_mock.add_exception(error)

        response = await fulltext.fulltext_search_api({"q": "hello"})
        assert response == {"error": "Unable to query search engine"}

    @pytest.mark.asyncio
    async def test_bad_json(self, httpx_mock, monkeypatch):
        url = "http://mock"
        monkeypatch.setattr(config, "plugin_inside", {"search_endpoint": url}, raising=False)
        httpx_mock.add_response(text="Not JSON")

        response = await fulltext.fulltext_search_api({"q": "hello"})
        assert response == {"error": "Error converting search engine data to JSON"}

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("page", "limit", "offset_kwarg", "expected_from"),
        [
            (1, 20, "NOT_PASSED", 0),  # offset not passed at all
            (1, 20, None, 0),  # offset=None explicitly
            (10, 20, "NOT_PASSED", 180),  # offset not passed, page 10
            (5, 20, 100, 100),  # explicit offset provided
        ],
    )
    async def test_pagination_offset_calculation(self, httpx_mock, monkeypatch, page, limit, offset_kwarg, expected_from):
        url = "http://mock"
        monkeypatch.setattr(config, "plugin_inside", {"search_endpoint": url}, raising=False)
        httpx_mock.add_response(json={"hits": {"hits": []}})

        # Conditionally build kwargs to test "not passed" scenario
        kwargs = {"page": page, "limit": limit}
        if offset_kwarg != "NOT_PASSED":
            kwargs["offset"] = offset_kwarg

        await fulltext.fulltext_search_async("test", **kwargs)
        request = httpx_mock.get_request()
        assert f"from={expected_from}" in request.url.query.decode()

    @pytest.mark.asyncio
    async def test_duplicate_ocaids_all_hydrate(self, httpx_mock, monkeypatch):
        """Two hits sharing an ocaid must both get the edition attached.

        The old ocaids.index() matching found only the first occurrence, so the
        second hit got no edition and was silently dropped by the templates.
        """
        url = "http://mock"
        monkeypatch.setattr(config, "plugin_inside", {"search_endpoint": url}, raising=False)
        httpx_mock.add_response(
            json={
                "hits": {
                    "total": 2,
                    "hits": [
                        {"fields": {"identifier": ["shared-ocaid"]}},
                        {"fields": {"identifier": ["shared-ocaid"]}},
                    ],
                }
            }
        )

        async def fake_availability(id_type, ocaids):
            return {"shared-ocaid": {"status": "open"}}

        monkeypatch.setattr(fulltext, "get_availability_async", fake_availability)

        edition = SimpleNamespace(ocaid="shared-ocaid", key="/books/OL1M")
        fake_site = SimpleNamespace(
            things=lambda q: ["/books/OL1M"],
            get_many=lambda keys: [edition],
        )
        monkeypatch.setattr(fulltext, "site", SimpleNamespace(get=lambda: fake_site))

        results = await fulltext.fulltext_search_async("test")
        hits = results["hits"]["hits"]
        assert [hit.get("edition") for hit in hits] == [edition, edition]
        assert [hit.get("availability") for hit in hits] == [{"status": "open"}, {"status": "open"}]


class Test_phrase_query:
    """Every query reaches the FTS backend as one straight-quoted phrase.

    The rules were measured against the backend: curly quotes aren't
    delimiters, an unbalanced quote degrades to bare words, an inner quote
    splits the phrase, and backslash escaping is inert.
    """

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            # The main case: no quotes at all.
            ("it was the best of times", '"it was the best of times"'),
            ("whale", '"whale"'),
            # Already a well-formed phrase: unchanged.
            ('"it was the best of times"', '"it was the best of times"'),
            ('"whale"', '"whale"'),
            # Curly quotes from a pasted passage, wrapping or inner.
            ("“it was the best of times”", '"it was the best of times"'),
            ("„it was the best of times‟", '"it was the best of times"'),
            ("he said “hello there” softly", '"he said hello there softly"'),
            # Unbalanced quotes, which the backend would silently ignore.
            ('"it was the best of times', '"it was the best of times"'),
            ('it was the best of times"', '"it was the best of times"'),
            ('hello there" softly', '"hello there softly"'),
            # Inner quotes (dialogue) can't be escaped, only removed.
            ('he said "hello there" softly', '"he said hello there softly"'),
            ('"he said "hello there" softly"', '"he said hello there softly"'),
            ('"he said \\"hello there\\" softly"', '"he said \\ hello there\\ softly"'),
            # Multiple phrases collapse into one — deliberate.
            ('"best of times" "worst of times"', '"best of times worst of times"'),
            # A quote with no space around it still splits into words.
            ('12"record', '"12 record"'),
            ('a""b', '"a b"'),
        ],
    )
    def test_wraps_in_straight_quotes(self, raw, expected):
        assert fulltext.phrase_query(raw) == expected

    @pytest.mark.parametrize(
        "raw",
        [
            "it's a truth universally acknowledged",
            "‘single’ and ’curly’ apostrophes",  # noqa: RUF001 — the curly marks are the point
            "golum AND smeagol",
            "war OR peace NOT famine",
            "title: the sea",
            "well-known fact",
            "and/or the",
            "who are you?",
            "(see figure 3)",
            "best of tim*",
            "foo \\ bar",
            "façade naïve über 日本語",
        ],
    )
    def test_everything_but_double_quotes_is_literal(self, raw):
        assert fulltext.phrase_query(raw) == f'"{raw}"'

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("  it was  the best ", '"it was the best"'),
            ("it was\nthe best\tof\r\ntimes", '"it was the best of times"'),
            ('" it was the best of times "', '"it was the best of times"'),
        ],
    )
    def test_collapses_whitespace(self, raw, expected):
        assert fulltext.phrase_query(raw) == expected

    @pytest.mark.parametrize("raw", [None, "", "   ", '"', '""', '"  "', "“”", " \n\t "])
    def test_nothing_to_search_is_empty(self, raw):
        assert fulltext.phrase_query(raw) == ""

    @pytest.mark.parametrize(
        "raw",
        [
            "it was the best of times",
            '"it was the best of times"',
            'he said "hello there" softly',
            "“curly”",
            "  spaced   out  ",
        ],
    )
    def test_idempotent(self, raw):
        once = fulltext.phrase_query(raw)
        assert fulltext.phrase_query(once) == once


@pytest.mark.usefixtures("request_context_fixture")
class Test_is_passage_query:
    """Mirrors isPassageQuery() in search-modal/fulltext.js: a quoted phrase
    or a PASSAGE_WORD_COUNT+ word query reads as a passage, not a title."""

    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            # A quoted phrase — straight or curly — is an explicit passage signal.
            ('"the best of times"', True),
            ("say “hello there” softly", True),
            ('a "b" c', True),
            # 5+ words reads as remembered passage text.
            ("it was the best of times", True),
            # Short unquoted queries read as title/author lookups.
            ("happiness paradox", False),
            ("one two three four", False),
            ("whale", False),
            # Empty or unbalanced quotes are not a phrase.
            ('""', False),
            ('"unbalanced quote', False),
            ("", False),
            ("   ", False),
        ],
    )
    def test_is_passage_query(self, query, expected):
        assert fulltext.is_passage_query(query) == expected


class Test_fulltext_search_async_phrasing:
    @pytest.fixture(autouse=True)
    def _req_context(self):
        # fulltext_search_api reads req_context (x-preferred-client-id header);
        # outside a request the ContextVar is deliberately unset — see
        # create_context_for_script's docstring.
        token = request_context.req_context.set(request_context.create_context_for_script())
        yield
        request_context.req_context.reset(token)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("raw", "sent"),
        [
            ("it was the best of times", '"it was the best of times"'),
            ('"it was the best of times"', '"it was the best of times"'),
            ('he said "hello there" softly', '"he said hello there softly"'),
            ("“it was the best of times”", '"it was the best of times"'),
        ],
    )
    async def test_backend_receives_phrase(self, httpx_mock, monkeypatch, raw, sent):
        monkeypatch.setattr(config, "plugin_inside", {"search_endpoint": "http://mock"}, raising=False)
        httpx_mock.add_response(json={"hits": {"hits": [], "total": 0}})

        await fulltext.fulltext_search_async(raw)

        request = httpx_mock.get_request()
        assert request.url.params["q"] == sent
        assert request.url.params["olonly"] == "true"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("raw", ["", "   ", '""', "“”", None])
    async def test_empty_phrase_skips_backend(self, httpx_mock, monkeypatch, raw):
        monkeypatch.setattr(config, "plugin_inside", {"search_endpoint": "http://mock"}, raising=False)

        results = await fulltext.fulltext_search_async(raw)

        assert results == {"hits": {"hits": [], "total": 0}}
        assert httpx_mock.get_request() is None
        assert fulltext.fulltext_page(results) == ([], 0)


def test_exclude_ocaids_drops_scans_already_on_the_page():
    rows = [fulltext.FulltextRow(ocaid, []) for ocaid in ("a", "b", "c")]
    assert [r.ocaid for r in fulltext.exclude_ocaids(rows, ["b", "missing"])] == ["a", "c"]
    assert fulltext.exclude_ocaids(rows, []) == rows
