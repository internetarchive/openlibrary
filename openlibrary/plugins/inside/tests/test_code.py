import pytest

from openlibrary.core import fulltext
from openlibrary.core.fulltext import filter_readable


def hit(ocaid: str) -> dict:
    return {"fields": {"identifier": [ocaid]}}


def test_readable_keeps_public_and_borrowable():
    hits = [hit("public"), hit("borrowable"), hit("restricted")]
    availability = {
        "public": {"is_readable": True, "is_lendable": False},
        "borrowable": {"is_readable": False, "is_lendable": True},
        "restricted": {"is_readable": False, "is_lendable": False, "is_printdisabled": True},
    }
    assert [h["fields"]["identifier"][0] for h in filter_readable(hits, availability)] == ["public", "borrowable"]


def test_readable_drops_hits_with_no_availability_record():
    # An unknown scan can't be shown as readable — but see the fail-open case
    # below: that's about the lookup failing wholesale, not one missing entry.
    assert filter_readable([hit("unknown")], {"other": {"is_readable": True}}) == []


def test_readable_fails_open_when_availability_lookup_failed():
    # Better a page of unfiltered results than an empty page.
    hits = [hit("public"), hit("restricted")]
    assert filter_readable(hits, {}) == hits


class FakeSearchAPI:
    """Captures the params fulltext_search_async sends upstream."""

    def __init__(self):
        self.params = None

    async def __call__(self, params):
        self.params = params
        return {"hits": {"hits": [], "total": 0}}


async def search_params(monkeypatch, **kwargs) -> dict:
    api = FakeSearchAPI()
    monkeypatch.setattr(fulltext, "fulltext_search_api", api)
    await fulltext.fulltext_search_async("moby dick", **kwargs)
    return api.params


@pytest.mark.asyncio
async def test_query_is_sent_verbatim_with_olonly(monkeypatch):
    # Nothing may be injected into `q`: a field clause would flip the endpoint
    # to its Lucene parser, which silently ignores olonly.
    params = await search_params(monkeypatch)
    assert params["q"] == "moby dick"
    assert params["olonly"] == "true"
    assert "lang" not in params


@pytest.mark.asyncio
async def test_language_is_sent_as_the_lang_param(monkeypatch):
    params = await search_params(monkeypatch, languages=["German"])
    assert params["q"] == "moby dick"
    assert params["lang"] == "German"


@pytest.mark.asyncio
async def test_only_the_first_language_is_sent(monkeypatch):
    # `lang=German,French` returns nothing upstream and a repeated param keeps
    # only the first, so one language is all we can honor.
    params = await search_params(monkeypatch, languages=["German", "French"])
    assert params["lang"] == "German"
