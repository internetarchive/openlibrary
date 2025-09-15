import pytest

from openlibrary.core import models


class MockSite:
    def get(self, key):
        return models.Thing(self, key, data={})

    def _get_backreferences(self, thing):
        return {}


class MockLendableEdition(models.Edition):
    def get_ia_collections(self):
        return ['inlibrary']


class MockPrivateEdition(models.Edition):
    def get_ia_collections(self):
        return ['inlibrary', 'georgetown-university-law-library-rr']


class TestEdition:
    def mock_edition(self, edition_class):
        data = {"key": "/books/OL1M", "type": {"key": "/type/edition"}, "title": "foo"}
        return edition_class(MockSite(), "/books/OL1M", data=data)

    def test_url(self):
        e = self.mock_edition(models.Edition)
        assert e.url() == "/books/OL1M/foo"
        assert e.url(v=1) == "/books/OL1M/foo?v=1"
        assert e.url(suffix="/add-cover") == "/books/OL1M/foo/add-cover"

        data = {
            "key": "/books/OL1M",
            "type": {"key": "/type/edition"},
        }
        e = models.Edition(MockSite(), "/books/OL1M", data=data)
        assert e.url() == "/books/OL1M/untitled"

    def test_get_ebook_info(self):
        e = self.mock_edition(models.Edition)
        assert e.get_ebook_info() == {}

    def test_is_not_in_private_collection(self):
        e = self.mock_edition(MockLendableEdition)
        assert not e.is_in_private_collection()

    def test_in_borrowable_collection_cuz_not_in_private_collection(self):
        e = self.mock_edition(MockLendableEdition)
        assert e.in_borrowable_collection()

    def test_is_in_private_collection(self):
        e = self.mock_edition(MockPrivateEdition)
        assert e.is_in_private_collection()

    def test_not_in_borrowable_collection_cuz_in_private_collection(self):
        e = self.mock_edition(MockPrivateEdition)
        assert not e.in_borrowable_collection()

    @pytest.mark.parametrize(
        ('isbn_or_asin', 'expected'),
        [
            ("1111111111", ("1111111111", "")),  # ISBN 10
            ("9780747532699", ("9780747532699", "")),  # ISBN 13
            ("B06XYHVXVJ", ("", "B06XYHVXVJ")),  # ASIN
            ("b06xyhvxvj", ("", "B06XYHVXVJ")),  # Lower case ASIN
            ("", ("", "")),  # Nothing at all.
        ],
    )
    def test_get_isbn_or_asin(self, isbn_or_asin, expected) -> None:
        e: models.Edition = self.mock_edition(MockPrivateEdition)
        got = e.get_isbn_or_asin(isbn_or_asin)
        assert got == expected

    @pytest.mark.parametrize(
        ('isbn', 'asin', 'expected'),
        [
            ("1111111111", "", True),  # ISBN 10
            ("", "B06XYHVXVJ", True),  # ASIN
            ("9780747532699", "", True),  # ISBN 13
            ("0", "", False),  # Invalid ISBN length
            ("", "0", False),  # Invalid ASIN length
            ("", "", False),  # Nothing at all.
        ],
    )
    def test_is_valid_identifier(self, isbn, asin, expected) -> None:
        e: models.Edition = self.mock_edition(MockPrivateEdition)
        got = e.is_valid_identifier(isbn=isbn, asin=asin)
        assert got == expected

    @pytest.mark.parametrize(
        ('isbn', 'asin', 'expected'),
        [
            ("1111111111", "", ["1111111111", "9781111111113"]),
            ("9780747532699", "", ["0747532699", "9780747532699"]),
            ("", "B06XYHVXVJ", ["B06XYHVXVJ"]),
            (
                "9780747532699",
                "B06XYHVXVJ",
                ["0747532699", "9780747532699", "B06XYHVXVJ"],
            ),
            ("", "", []),
        ],
    )
    def test_get_identifier_forms(
        self, isbn: str, asin: str, expected: list[str]
    ) -> None:
        e: models.Edition = self.mock_edition(MockPrivateEdition)
        got = e.get_identifier_forms(isbn=isbn, asin=asin)
        assert got == expected


class TestAuthor:
    def test_url(self):
        data = {"key": "/authors/OL1A", "type": {"key": "/type/author"}, "name": "foo"}

        e = models.Author(MockSite(), "/authors/OL1A", data=data)

        assert e.url() == "/authors/OL1A/foo"
        assert e.url(v=1) == "/authors/OL1A/foo?v=1"
        assert e.url(suffix="/add-photo") == "/authors/OL1A/foo/add-photo"

        data = {
            "key": "/authors/OL1A",
            "type": {"key": "/type/author"},
        }
        e = models.Author(MockSite(), "/authors/OL1A", data=data)
        assert e.url() == "/authors/OL1A/unnamed"


class TestSubject:
    def test_url(self):
        subject = models.Subject({"key": "/subjects/love"})
        assert subject.url() == "/subjects/love"
        assert subject.url("/lists") == "/subjects/love/lists"


class TestWork:
    def test_resolve_redirect_chain(self, monkeypatch):
        # e.g. https://openlibrary.org/works/OL2163721W.json

        # Chain:
        type_redir = {"key": "/type/redirect"}
        type_work = {"key": "/type/work"}
        work1_key = "/works/OL123W"
        work2_key = "/works/OL234W"
        work3_key = "/works/OL345W"
        work4_key = "/works/OL456W"
        work1 = {"key": work1_key, "location": work2_key, "type": type_redir}
        work2 = {"key": work2_key, "location": work3_key, "type": type_redir}
        work3 = {"key": work3_key, "location": work4_key, "type": type_redir}
        work4 = {"key": work4_key, "type": type_work}

        import web  # noqa: PLC0415

        from openlibrary.mocks import mock_infobase  # noqa: PLC0415

        site = mock_infobase.MockSite()
        site.save(web.storage(work1))
        site.save(web.storage(work2))
        site.save(web.storage(work3))
        site.save(web.storage(work4))
        monkeypatch.setattr(web.ctx, "site", site, raising=False)

        work_key = "/works/OL123W"
        redirect_chain = models.Work.get_redirect_chain(work_key)
        assert redirect_chain
        resolved_work = redirect_chain[-1]
        assert (
            str(resolved_work.type) == type_work['key']
        ), f"{resolved_work} of type {resolved_work.type} should be {type_work['key']}"
        assert resolved_work.key == work4_key, f"Should be work4.key: {resolved_work}"
