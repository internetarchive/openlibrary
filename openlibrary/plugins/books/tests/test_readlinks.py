import pytest
import web

from openlibrary.plugins.books import readlinks


@pytest.mark.parametrize(
    ("ebook_access", "options", "expected"),
    [
        ("borrowable", {}, "lendable"),
        ("printdisabled", {}, "restricted"),
        ("public", {}, "full access"),
        ("no_ebook", {}, "full access"),
        (None, {}, "full access"),
    ],
)
def test_get_item_status(ebook_access, options, expected, mock_site):
    read_processor = readlinks.ReadProcessor(options=options)
    status = read_processor.get_item_status("ekey", "iaid", ebook_access)
    assert status == expected


@pytest.mark.parametrize(
    ("borrowed", "expected"),
    [
        ("true", "checked out"),
        ("false", "lendable"),
    ],
)
def test_get_item_status_monkeypatched(borrowed, expected, monkeypatch, mock_site):
    read_processor = readlinks.ReadProcessor(options={})
    monkeypatch.setattr(web.ctx.site.store, "get", lambda _, __: {"borrowed": borrowed})
    status = read_processor.get_item_status("ekey", "iaid", "borrowable")
    assert status == expected


def test_get_readitem_missing_when_not_in_solr(mock_site):
    rp = readlinks.ReadProcessor(options={})
    rp.iaid_to_ebook_access = {}
    rp.iaid_to_ed = {}
    result = rp.get_readitem("some_iaid", "some_iaid", "/books/OL1M", "/works/OL1W", "missing", "2000")
    assert result is None


def test_get_readitem_present_when_in_solr(mock_site):
    rp = readlinks.ReadProcessor(options={"show_all_items": True})
    rp.iaid_to_ebook_access = {"myiaid": "public"}
    rp.iaid_to_ed = {"myiaid": {"key": "/books/OL1M", "covers": []}}
    result = rp.get_readitem("myiaid", "myiaid", "/books/OL1M", "/works/OL1W", "full access", "2000")
    assert result is not None
    assert result["status"] == "full access"
