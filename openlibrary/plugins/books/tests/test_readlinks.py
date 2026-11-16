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
