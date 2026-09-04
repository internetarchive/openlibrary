import asyncio
import datetime

import pytest

from openlibrary.coverstore_fastapi import lookup, utils
from openlibrary.coverstore_fastapi.utils import DisallowedCoverUrl


def test_safeint():
    assert utils.safeint("12") == 12
    assert utils.safeint("-3") == -3
    assert utils.safeint(None) is None
    assert utils.safeint("abc") is None
    assert utils.safeint("abc", 7) == 7


def test_random_string():
    s = utils.random_string(10)
    assert len(s) == 10
    allowed = set(utils.chars)
    assert set(s) <= allowed


def test_httpdate_roundtrip():
    dt = datetime.datetime(2026, 1, 2, 3, 4, 5)
    formatted = utils.httpdate(dt)
    assert formatted == "Fri, 02 Jan 2026 03:04:05 GMT"
    assert utils.parse_httpdate(formatted) == dt


def test_parse_httpdate_invalid():
    assert utils.parse_httpdate("not a date") is None
    assert utils.parse_httpdate("") is None


def test_urldecode():
    base, params = utils.urldecode("http://google.com/search?q=bar&x=y")
    assert base == "http://google.com/search"
    assert params == {"q": "bar", "x": "y"}

    base, params = utils.urldecode("http://google.com/")
    assert base == "http://google.com/"
    assert params == {}


def test_changequery_updates_and_adds():
    url = utils.changequery("http://g.com/search?q=foo", q="bar", x="y")
    assert url == "http://g.com/search?q=bar&x=y"


def test_changequery_on_path_only_url():
    url = utils.changequery("/", errcode=1, errmsg="No image found")
    assert url == "/?errcode=1&errmsg=No+image+found"


def test_zipview_url_original():
    assert lookup.zipview_url_from_id(123_456_789, "", "https") == "https://archive.org/download/olcovers12345/olcovers12345.zip/123456789.jpg"


def test_zipview_url_sized():
    assert lookup.zipview_url_from_id(777001, "M", "http") == "http://archive.org/download/olcovers77/olcovers77-M.zip/777001-M.jpg"


def test_archive_cluster_url_original():
    assert lookup.archive_cluster_url(8_123_456, size="", protocol="https") == "https://archive.org/download/covers_0008/covers_0008_12.zip/0008123456.jpg"


def test_archive_cluster_url_sized():
    assert lookup.archive_cluster_url(8_000_000, size="L", protocol="http") == "http://archive.org/download/l_covers_0008/l_covers_0008_00.zip/0008000000-L.jpg"


def test_is_allowed_cover_url():
    assert utils.is_allowed_cover_url("https://archive.org/download/goody/page/cover_w500_h500.jpg")
    assert utils.is_allowed_cover_url("http://books.google.com/books?id=x")
    assert not utils.is_allowed_cover_url("http://evil.example.com/x.jpg")
    assert not utils.is_allowed_cover_url("ftp://archive.org/download/goody/page/cover.jpg")


def test_download_external_image_disallowed():
    # Must reject before any network access happens.
    with pytest.raises(DisallowedCoverUrl):
        asyncio.run(lookup.download_external_image("http://evil.example.com/x.jpg"))
