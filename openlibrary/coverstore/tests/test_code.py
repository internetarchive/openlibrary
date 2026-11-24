import datetime as dt
from io import StringIO

import web

from .. import code, utils


class TestServeDefaultOpenRedirect:
    """GHSA-8ffj: ``?default=<url>`` on the cover endpoints must not become a 303
    open redirect to an arbitrary host (phishing under OL's trusted domain)."""

    def test_rejects_external_open_redirect(self):
        resp = code._serve_default("https://evil.example.com/phish")
        assert resp.status_code != 303
        assert resp.headers.get("location") != "https://evil.example.com/phish"

    def test_rejects_scheme_relative_open_redirect(self):
        resp = code._serve_default("//evil.example.com/phish")
        assert resp.status_code != 303

    def test_rejects_lookalike_host(self):
        resp = code._serve_default("https://openlibrary.org.evil.example.com/phish")
        assert resp.status_code != 303

    def test_rejects_backslash_authority_confusion(self):
        # urlsplit sees host=openlibrary.org (trusted), but a WHATWG browser
        # normalises "\" to "/" and navigates to evil.example.com. The guard
        # must reject the raw backslash rather than validate a different string.
        resp = code._serve_default("https://evil.example.com\\@openlibrary.org/phish")
        assert resp.status_code != 303

    def test_allows_trusted_fallback_redirect(self):
        # The real, legitimate use: OL/IA static fallback images.
        url = "https://openlibrary.org/static/images/icons/avatar_book.png"
        resp = code._serve_default(url)
        assert resp.status_code == 303
        assert resp.headers["location"] == url

    def test_allows_allowed_cover_host_redirect(self):
        url = "https://covers.openlibrary.org/b/id/15082914-M.jpg"
        resp = code._serve_default(url)
        assert resp.status_code == 303
        assert resp.headers["location"] == url

    def test_plain_false_default_is_404(self):
        assert code._serve_default("false").status_code == 404


class TestSafeRedirectTarget:
    """POST siblings (touch/delete/upload) 303 to a user-controlled
    redirect_url/success_url/referer. utils.safe_redirect_target neutralises the
    open redirect while preserving same-site and trusted-host targets."""

    def test_relative_path_allowed(self):
        assert utils.safe_redirect_target("/books/OL1M") == "/books/OL1M"

    def test_trusted_host_allowed(self):
        url = "https://openlibrary.org/books/OL1M"
        assert utils.safe_redirect_target(url) == url

    def test_external_host_falls_back(self):
        assert utils.safe_redirect_target("https://evil.example.com/x") == "/"

    def test_scheme_relative_falls_back(self):
        assert utils.safe_redirect_target("//evil.example.com/x") == "/"

    def test_backslash_authority_confusion_falls_back(self):
        assert utils.safe_redirect_target("https://evil.example.com\\@openlibrary.org/x") == "/"

    def test_none_falls_back(self):
        assert utils.safe_redirect_target(None) == "/"


def test_tarindex_path():
    assert code.get_tarindex_path(0, "") == "items/covers_0000/covers_0000_00.index"
    assert code.get_tarindex_path(0, "s") == "items/s_covers_0000/s_covers_0000_00.index"
    assert code.get_tarindex_path(0, "m") == "items/m_covers_0000/m_covers_0000_00.index"
    assert code.get_tarindex_path(0, "l") == "items/l_covers_0000/l_covers_0000_00.index"

    assert code.get_tarindex_path(99, "") == "items/covers_0000/covers_0000_99.index"
    assert code.get_tarindex_path(100, "") == "items/covers_0001/covers_0001_00.index"

    assert code.get_tarindex_path(1, "") == "items/covers_0000/covers_0000_01.index"
    assert code.get_tarindex_path(21, "") == "items/covers_0000/covers_0000_21.index"
    assert code.get_tarindex_path(321, "") == "items/covers_0003/covers_0003_21.index"
    assert code.get_tarindex_path(4321, "") == "items/covers_0043/covers_0043_21.index"


def test_parse_tarindex():
    f = StringIO("")

    offsets, sizes = code.parse_tarindex(f)
    assert list(offsets) == [0 for i in range(10000)]
    assert list(sizes) == [0 for i in range(10000)]

    f = StringIO("0000010000.jpg\t0\t10\n0000010002.jpg\t512\t20\n")

    offsets, sizes = code.parse_tarindex(f)
    assert (offsets[0], sizes[0]) == (0, 10)
    assert (offsets[1], sizes[1]) == (0, 0)
    assert (offsets[2], sizes[2]) == (512, 20)
    assert (offsets[42], sizes[42]) == (0, 0)


class TestCoverLookup:
    def test_get_tar_filename(self, monkeypatch):
        offsets = {}
        sizes = {}

        def _get_tar_index(index, size):
            array_offsets = [offsets.get(i, 0) for i in range(10000)]
            array_sizes = [sizes.get(i, 0) for i in range(10000)]
            return array_offsets, array_sizes

        monkeypatch.setattr(code, "get_tar_index", _get_tar_index)
        f = code.get_tar_filename

        assert f(42, "s") is None

        offsets[42] = 1234
        sizes[42] = 567

        assert f(42, "s") == "s_covers_0000_00.tar:1234:567"
        assert f(30042, "s") == "s_covers_0000_03.tar:1234:567"

        d = code.get_details(42, "s")
        assert isinstance(d, web.storage)
        assert d == {
            "id": 42,
            "filename_s": "s_covers_0000_00.tar:1234:567",
            "created": dt.datetime(2010, 1, 1),
        }
