import asyncio
import time

import pytest
from pymemcache.test.utils import MockMemcacheClient

from openlibrary.core import ia
from openlibrary.plugins.books import dynlinks, readlinks


@pytest.mark.parametrize(
    ("collections", "options", "expected"),
    [
        (["inlibrary"], {}, "lendable"),
        (["printdisabled"], {}, "restricted"),
        (["some other collection"], {}, "full access"),
    ],
)
def test_get_item_status(collections, options, expected, mock_site):
    read_processor = readlinks.ReadProcessor(options=options)
    status = read_processor.get_item_status("ekey", "iaid", collections)
    assert status == expected


@pytest.mark.parametrize(
    ("checked_out_ocaids", "expected"),
    [
        ({"iaid"}, "checked out"),
        (frozenset(), "lendable"),
    ],
)
def test_get_item_status_checked_out(checked_out_ocaids, expected, mock_site):
    read_processor = readlinks.ReadProcessor(options={})
    read_processor.checked_out_ocaids = checked_out_ocaids
    collections = ["inlibrary"]
    status = read_processor.get_item_status("ekey", "iaid", collections)
    assert status == expected


@pytest.mark.asyncio
async def test_readlinks_forwards_base_url(monkeypatch, mock_site):
    captured = {}

    class FakeReadProcessor:
        def __init__(self, options, base_url=None):
            captured["base_url"] = base_url

        async def process(self, req):
            return {}

    monkeypatch.setattr(readlinks, "ReadProcessor", FakeReadProcessor)

    result = await readlinks.readlinks("isbn:1234567890", {}, base_url="http://example.com")

    assert captured["base_url"] == "http://example.com"
    assert result == {}


IA_METADATA = {
    "ia-full": {"metadata": {"identifier": "ia-full", "collection": ["americana"]}},
    "ia-lendable": {"metadata": {"identifier": "ia-lendable", "collection": ["inlibrary", "printdisabled"]}},
    "ia-checkedout": {"metadata": {"identifier": "ia-checkedout", "collection": ["inlibrary", "printdisabled"]}},
    "ia-restricted": {"metadata": {"identifier": "ia-restricted", "collection": ["printdisabled"]}},
    # ia-gone: archive.org returns no metadata for it (timeout, error or dark item).
}


def ia_metadata_response(url, params=None):
    return IA_METADATA.get(url.rsplit("/", 1)[-1], {})


def setup_read_api(monkeypatch, mock_site):
    """One work with five scanned editions, and everything ReadProcessor.process talks to mocked."""
    mock_site.save({"key": "/works/OL1W", "type": {"key": "/type/work"}, "title": "A Work"})
    for i, ocaid in enumerate(["ia-full", "ia-lendable", "ia-checkedout", "ia-restricted", "ia-gone"], start=1):
        mock_site.save(
            {
                "key": f"/books/OL{i}M",
                "type": {"key": "/type/edition"},
                "title": f"Edition {i}",
                "works": [{"key": "/works/OL1W"}],
                "ocaid": ocaid,
                "publish_date": str(1990 + i),
                "covers": [i],
            }
        )

    things = mock_site.things

    def things_with_list_values(query):
        # MockSite can't match a list of values; Infobase matches any of them.
        if isinstance(ocaids := query.get("ocaid"), list):
            return sorted(key for ocaid in ocaids for key in things({**query, "ocaid": ocaid}))
        return things(query)

    monkeypatch.setattr(mock_site, "things", things_with_list_values)

    async def query_docs(bib_keys):
        return {k: mock_site.get("/books/OL2M").dict() for k in bib_keys if k == "olid:OL2M"}

    async def add_availability(docs):
        return {k: {**doc, "preview": "borrow"} for k, doc in docs.items()}

    async def get_checked_out(ocaids):
        return {"ia-checkedout"} & set(ocaids)

    async def get_solr_fields_for_works(field, wkeys, clip_limit=None):
        return {"/works/OL1W": ["ia-full", "ia-lendable", "ia-checkedout", "ia-restricted", "ia-gone"]}

    monkeypatch.setattr(dynlinks, "query_docs", query_docs)
    monkeypatch.setattr(dynlinks, "add_availability", add_availability)
    monkeypatch.setattr(dynlinks.lending, "get_checked_out_async", get_checked_out)
    monkeypatch.setattr(readlinks, "get_solr_fields_for_works", get_solr_fields_for_works)
    monkeypatch.setattr(ia.get_metadata, "_memcache", MockMemcacheClient())


@pytest.mark.asyncio
@pytest.mark.parametrize("options", [{}, {"show_all_items": True}])
async def test_process_output_unchanged_by_async_metadata(monkeypatch, mock_site, options):
    setup_read_api(monkeypatch, mock_site)
    monkeypatch.setattr(ia, "get_api_response", ia_metadata_response)

    async def get_api_response_async(url, params=None):
        return ia_metadata_response(url)

    monkeypatch.setattr(ia, "get_api_response_async", get_api_response_async)

    # The new, concurrent lookup...
    new = await readlinks.ReadProcessor(options).process("olid:OL2M")

    # ...against the sequential one it replaced, on an empty cache.
    async def get_metadata_sequentially(iaids):
        return {iaid: ia.get_metadata(iaid) for iaid in iaids}

    monkeypatch.setattr(ia.get_metadata, "_memcache", MockMemcacheClient())
    monkeypatch.setattr(ia, "get_metadata_many_async", get_metadata_sequentially)
    old = await readlinks.ReadProcessor(options).process("olid:OL2M")

    assert new == old
    statuses = {item["ol-edition-id"]: item["status"] for item in new["olid:OL2M"]["items"]}
    if options:
        assert statuses == {"OL1M": "full access", "OL2M": "lendable", "OL3M": "checked out", "OL4M": "restricted"}
    else:
        assert statuses == {"OL1M": "full access", "OL2M": "lendable"}


@pytest.mark.asyncio
async def test_process_fetches_ia_metadata_concurrently(monkeypatch, mock_site):
    setup_read_api(monkeypatch, mock_site)

    async def slow_get_api_response_async(url, params=None):
        await asyncio.sleep(0.2)
        return ia_metadata_response(url)

    monkeypatch.setattr(ia, "get_api_response_async", slow_get_api_response_async)

    start = time.monotonic()
    result = await readlinks.ReadProcessor({}).process("olid:OL2M")
    elapsed = time.monotonic() - start

    assert elapsed < 0.6  # five scans fetched at once, not one after another (1 s)
    assert [item["ol-edition-id"] for item in result["olid:OL2M"]["items"]] == ["OL2M", "OL1M"]  # the requested edition first
