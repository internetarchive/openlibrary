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
