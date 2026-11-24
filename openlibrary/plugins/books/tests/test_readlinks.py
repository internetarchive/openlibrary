import asyncio
import threading

import pytest

from openlibrary.plugins.books import readlinks


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


@pytest.mark.asyncio
async def test_process_fetches_ia_metadata_off_the_event_loop(monkeypatch, mock_site):
    loop_ran = threading.Event()

    def get_metadata(iaid):
        # Waits for a coroutine that can only run if this call isn't holding the event loop.
        assert loop_ran.wait(timeout=5), "ia.get_metadata blocked the event loop"
        return {"collection": ["inlibrary"]}

    async def no_docs(bib_keys):
        return {}

    async def same_docs(docs):
        return docs

    async def nothing_checked_out(ocaids):
        return set()

    async def get_solr_fields_for_works(field, wkeys, clip_limit=None):
        return {"/works/OL1W": ["ia1", "ia2"]}

    monkeypatch.setattr(readlinks.dynlinks, "query_docs", no_docs)
    monkeypatch.setattr(readlinks.dynlinks, "add_availability", same_docs)
    monkeypatch.setattr(readlinks.lending, "get_checked_out_async", nothing_checked_out)
    monkeypatch.setattr(readlinks, "get_solr_fields_for_works", get_solr_fields_for_works)
    monkeypatch.setattr(readlinks.ia, "get_metadata", get_metadata)

    async def run_on_loop():
        loop_ran.set()

    processor = readlinks.ReadProcessor({})
    await asyncio.gather(processor.process("olid:OL1M"), run_on_loop())

    assert processor.iaid_to_meta == {"ia1": {"collection": ["inlibrary"]}, "ia2": {"collection": ["inlibrary"]}}
