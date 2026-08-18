"""Tests for the `<ol-books-display>` endpoints and card normalization."""

from unittest.mock import patch

import pytest
import web

from openlibrary.fastapi.services import books_display as svc

SERVICE = "openlibrary.fastapi.services.books_display"


def solr_work(**overrides):
    work = {
        "key": "/works/OL1W",
        "title": "Project Hail Mary",
        "author_name": ["Andy Weir"],
        "author_key": ["OL7W1A"],
        "cover_i": 123,
        "first_publish_year": 2021,
        "ratings_average": 4.3,
        "ratings_count": 3662,
        "editions": {"docs": [{"key": "/books/OL9M", "cover_i": 456, "ia": ["projecthailmary"], "ebook_access": "borrowable"}]},
    }
    work.update(overrides)
    return work


@pytest.fixture(autouse=True)
def _cover_host():
    with patch(f"{SERVICE}.get_coverstore_public_url", return_value="https://covers.test"):
        yield


class TestToBookCard:
    def test_flattens_work_and_edition(self):
        card = svc.to_book_card(solr_work())
        assert card["key"] == "/works/OL1W"
        assert card["title"] == "Project Hail Mary"
        assert card["authors"] == [{"key": "/authors/OL7W1A", "name": "Andy Weir"}]
        assert card["cover_url"] == "https://covers.test/b/id/123-M.jpg"  # work cover wins
        assert card["edition_key"] == "OL9M"
        assert card["first_publish_year"] == 2021
        assert card["ratings_average"] == 4.3
        assert card["ratings_count"] == 3662

    def test_author_without_key(self):
        card = svc.to_book_card(solr_work(author_key=[]))
        assert card["authors"] == [{"key": None, "name": "Andy Weir"}]

    def test_cover_falls_back_to_ia_then_olid(self):
        assert svc._cover_url({"ia": ["abc"]}, {}) == "https://covers.test/b/ia/abc-M.jpg?default=false"
        assert svc._cover_url({"cover_edition_key": "OL5M"}, {}) == "https://covers.test/b/olid/OL5M-M.jpg"
        assert svc._cover_url({"cover_i": -1}, {}) is None


class TestBuildAccess:
    """`build_access` mirrors LoanStatus.html branch by branch."""

    def edition(self, availability=None, **extra):
        return {"key": "/books/OL9M", "ia": ["x"], "availability": availability, **extra}

    def access(self, state, availability=None, **extra):
        with patch(f"{SERVICE}.get_lending_state", return_value=state):
            return svc.build_access(self.edition(availability, **extra))

    def test_open(self):
        a = self.access("open", {"identifier": "x"})
        assert (a["cta"], a["url"], a["badge"], a["login_intent"]) == ("read", "/borrow/ia/x?ref=ol", None, False)

    def test_borrowable_requires_login_intent(self):
        a = self.access("borrowable", {"identifier": "x"})
        assert (a["cta"], a["url"], a["login_intent"]) == ("borrow", "/borrow/ia/x?ref=ol", True)

    def test_waitlist_is_a_post(self):
        a = self.access("waitlist", {"identifier": "x"})
        assert (a["cta"], a["url"], a["method"]) == ("join_waitlist", "/borrow/ia/x", "post")

    def test_preview_only_badge_and_external(self):
        a = self.access("preview_only", {"identifier": "x"})
        assert (a["cta"], a["badge"], a["external"]) == ("preview", "preview", True)
        assert a["url"] == "https://archive.org/details/x"

    def test_printdisabled_with_standard_borrow(self):
        a = self.access("printdisabled", {"identifier": "x", "available_to_borrow": True})
        assert a["cta"] == "borrow"
        a = self.access("printdisabled", {"identifier": "x"})
        assert a["cta"] == "special_access"

    def test_checked_out_has_no_url(self):
        a = self.access("checkedout", {"identifier": "x"})
        assert (a["cta"], a["url"]) == ("checked_out", None)

    def test_locate(self):
        a = self.access("locate")
        assert (a["cta"], a["badge"], a["external"]) == ("find_in_library", "not_online", True)
        assert a["url"] == "/books/OL9M/-/borrow?action=locate"

    def test_locate_without_edition_key_is_not_in_library(self):
        with patch(f"{SERVICE}.get_lending_state", return_value="locate"):
            a = svc.build_access({"key": "/works/OL1W"})
        assert (a["cta"], a["url"], a["badge"]) == ("not_in_library", None, "not_online")

    def test_partner_open_access(self):
        edition = {"key": "/books/OL9M", "id_standard_ebooks": ["foo/bar"], "ebook_access": "public"}
        with patch(f"{SERVICE}.get_lending_state", return_value="partner"):
            a = svc.build_access(edition)
        assert (a["state"], a["cta"], a["external"]) == ("partner", "read", True)
        assert a["url"] == "/books/OL9M/-/borrow?action=read"


class TestBooksDisplayEndpoint:
    def test_returns_cards(self, fastapi_client):
        raw = {"docs": [solr_work()], "num_found": 1}
        with (
            patch(f"{SERVICE}._fetch_raw_docs", return_value=raw) as fetch,
            patch(f"{SERVICE}.get_lending_state", return_value="locate"),
            patch("openlibrary.fastapi.books_display.accounts.get_current_user", return_value=None),
        ):
            response = fastapi_client.get("/books-display.json", params={"q": "subject:fiction", "sort": "trending", "limit": 5, "offset": 10})
        assert response.status_code == 200
        body = response.json()
        assert body["num_found"] == 1
        assert (body["offset"], body["limit"]) == (10, 5)
        assert body["docs"][0]["title"] == "Project Hail Mary"
        assert body["docs"][0]["access"]["cta"] == "find_in_library"
        fetch.assert_called_once_with("subject:fiction", "trending", 5, 10, True, True)

    def test_limit_is_capped(self, fastapi_client):
        response = fastapi_client.get("/books-display.json", params={"q": "x", "limit": 500})
        assert response.status_code == 422


class TestUserStateEndpoint:
    def test_requires_login(self, fastapi_client):
        response = fastapi_client.get("/books-display/user-state.json", params={"work_ids": "OL1W"})
        assert response.status_code == 401

    def test_returns_shelves_and_ratings(self, fastapi_client, mock_authenticated_user):
        rows = [web.storage(work_id=1, bookshelf_id=2)]
        with (
            patch("openlibrary.fastapi.books_display.Bookshelves.get_users_read_status_of_works", return_value=rows) as shelves,
            patch("openlibrary.fastapi.books_display.Ratings.get_users_ratings_of_works", return_value={2: 5}) as ratings,
        ):
            response = fastapi_client.get("/books-display/user-state.json", params={"work_ids": "OL1W,OL2W"})
        assert response.status_code == 200
        assert response.json() == {"shelves": {"OL1W": 2}, "ratings": {"OL2W": 5}}
        shelves.assert_called_once_with("testuser", [1, 2])
        ratings.assert_called_once_with("testuser", [1, 2])
