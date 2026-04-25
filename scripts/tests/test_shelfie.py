"""Tests for scripts/shelfie.py — pure helpers and the merge-save logic
that protects against the bug where partial saves clobber existing fields
(see PR #12157 review, bug #5)."""

import sys
from unittest.mock import MagicMock, patch

import requests

# shelfie imports _init_path for its side-effect; stub it in the test env.
sys.modules["_init_path"] = MagicMock()

from ..shelfie import (
    _coverless_works_from_solr,
    _find_prod_cover_id,
    _guess_password,
    _is_low_quality,
    _merge_save,
    _pick_publisher,
    _search_doc_to_record,
    cmd_list_users,
    cmd_populate_covers,
)


class TestIsLowQuality:
    def test_rejects_study_guide_title(self):
        assert _is_low_quality({"title": "Study Guide to Moby-Dick"})

    def test_rejects_workbook_title(self):
        assert _is_low_quality({"title": "Algebra II Workbook"})

    def test_rejects_self_published_publisher(self):
        assert _is_low_quality({"title": "My Book", "publisher": ["Independently published"]})

    def test_rejects_createspace(self):
        assert _is_low_quality({"title": "My Book", "publisher": ["CreateSpace"]})

    def test_accepts_normal_book(self):
        assert not _is_low_quality({"title": "Pride and Prejudice", "publisher": ["Penguin Classics"]})

    def test_accepts_mixed_publishers(self):
        # As long as one real publisher exists, don't reject.
        assert not _is_low_quality({"title": "Some Book", "publisher": ["Independently published", "Vintage"]})


class TestPickPublisher:
    def test_skips_rejected_and_returns_first_real(self):
        assert _pick_publisher({"publisher": ["Independently published", "Penguin", "Vintage"]}) == ["Penguin"]

    def test_fallback_when_empty(self):
        assert _pick_publisher({"publisher": []}) == ["Unknown"]

    def test_fallback_when_missing(self):
        assert _pick_publisher({}) == ["Unknown"]

    def test_fallback_when_all_rejected(self):
        assert _pick_publisher({"publisher": ["Independently published", "CreateSpace"]}) == ["Unknown"]


class TestSearchDocToRecord:
    def test_minimal_doc(self):
        rec = _search_doc_to_record({"title": "Hi"}, "shelfie:tag")
        assert rec["title"] == "Hi"
        assert rec["authors"] == [{"name": "Unknown"}]
        assert rec["source_records"] == ["shelfie:tag"]

    def test_isbn_13_routing(self):
        rec = _search_doc_to_record({"title": "X", "isbn": ["9780140449136"]}, "tag")
        assert rec["isbn_13"] == ["9780140449136"]
        assert "isbn_10" not in rec

    def test_isbn_10_routing(self):
        rec = _search_doc_to_record({"title": "X", "isbn": ["0140449132"]}, "tag")
        assert rec["isbn_10"] == ["0140449132"]
        assert "isbn_13" not in rec

    def test_cover_url(self):
        rec = _search_doc_to_record({"title": "X", "cover_i": 42}, "tag")
        assert rec["cover"] == "https://covers.openlibrary.org/b/id/42-L.jpg"

    def test_no_cover_when_missing(self):
        rec = _search_doc_to_record({"title": "X"}, "tag")
        assert "cover" not in rec

    def test_subjects_capped_at_ten(self):
        doc = {"title": "X", "subject": [f"s{i}" for i in range(20)]}
        rec = _search_doc_to_record(doc, "tag")
        assert len(rec["subjects"]) == 10


class TestMergeSave:
    """Regression test for PR #12157 bug #5 — partial saves wiping fields."""

    def test_preserves_existing_fields(self):
        existing = {
            "key": "/works/OL1W",
            "type": {"key": "/type/work"},
            "title": "Catching Fire",
            "subjects": ["Dystopia", "Young Adult"],
            "authors": [{"key": "/authors/OL1A"}],
            "covers": [135],
            "revision": 1,
            "latest_revision": 1,
            "created": {"type": "/type/datetime", "value": "2026-01-01T00:00:00"},
            "last_modified": {"type": "/type/datetime", "value": "2026-01-01T00:00:00"},
        }
        new_patch = {
            "key": "/works/OL1W",
            "type": {"key": "/type/work"},
            "series": [{"series": {"key": "/series/OL9L"}, "position": "2"}],
        }

        with (
            patch("scripts.shelfie._fetch_raw", return_value=existing),
            patch("scripts.shelfie.infobase_save") as mock_save,
        ):
            _merge_save([new_patch])

        saved_docs = mock_save.call_args[0][0]
        assert len(saved_docs) == 1
        saved = saved_docs[0]

        # All prior fields retained
        assert saved["title"] == "Catching Fire"
        assert saved["subjects"] == ["Dystopia", "Young Adult"]
        assert saved["authors"] == [{"key": "/authors/OL1A"}]
        assert saved["covers"] == [135]
        # New field applied
        assert saved["series"] == new_patch["series"]
        # Revision metadata stripped so save_many will accept the doc
        assert "revision" not in saved
        assert "latest_revision" not in saved
        assert "created" not in saved
        assert "last_modified" not in saved

    def test_patch_overrides_existing_field(self):
        existing = {
            "key": "/works/OL1W",
            "type": {"key": "/type/work"},
            "subjects": ["old"],
        }
        new_patch = {
            "key": "/works/OL1W",
            "type": {"key": "/type/work"},
            "subjects": ["new"],
        }

        with (
            patch("scripts.shelfie._fetch_raw", return_value=existing),
            patch("scripts.shelfie.infobase_save") as mock_save,
        ):
            _merge_save([new_patch])

        saved = mock_save.call_args[0][0][0]
        assert saved["subjects"] == ["new"]

    def test_fetch_failure_uses_empty_base(self):
        """If the existing doc can't be fetched, the patch still saves on its own
        (rather than exploding). This is a degraded path — not ideal but safer
        than crashing mid-batch."""
        new_patch = {
            "key": "/works/OL9999W",
            "type": {"key": "/type/work"},
            "series": [{"series": {"key": "/series/OL1L"}, "position": "1"}],
        }

        with (
            patch("scripts.shelfie._fetch_raw", return_value=None),
            patch("scripts.shelfie.infobase_save") as mock_save,
        ):
            _merge_save([new_patch])

        saved = mock_save.call_args[0][0][0]
        assert saved == new_patch


class TestCoverlessWorksFromSolr:
    def test_parses_solr_response(self):
        fake = {
            "response": {
                "docs": [
                    {"key": "/works/OL1W", "title": "Book 1", "author_name": ["Author A"]},
                    {"key": "/works/OL2W", "title": "Book 2"},
                ]
            }
        }
        with patch("scripts.shelfie.solr_request", return_value=fake):
            assert _coverless_works_from_solr(limit=50) == [
                ("/works/OL1W", "Book 1", "Author A"),
                ("/works/OL2W", "Book 2", ""),
            ]

    def test_skips_docs_missing_key_or_title(self):
        fake = {
            "response": {
                "docs": [
                    {"key": "/works/OL1W"},
                    {"title": "Orphan"},
                    {"key": "/works/OL3W", "title": "Good", "author_name": ["A"]},
                ]
            }
        }
        with patch("scripts.shelfie.solr_request", return_value=fake):
            assert _coverless_works_from_solr() == [("/works/OL3W", "Good", "A")]

    def test_empty_when_solr_unavailable(self):
        with patch("scripts.shelfie.solr_request", return_value=None):
            assert _coverless_works_from_solr() == []

    def test_empty_when_response_missing(self):
        with patch("scripts.shelfie.solr_request", return_value={}):
            assert _coverless_works_from_solr() == []


class TestFindProdCoverId:
    def _mock_response(self, docs):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"docs": docs}
        return resp

    def test_returns_first_cover_id(self):
        resp = self._mock_response([{"key": "/works/X", "cover_i": 42}])
        with patch("scripts.shelfie.requests.get", return_value=resp) as mock_get:
            assert _find_prod_cover_id("Dune", "Herbert") == 42
        # Author should be passed when given
        assert mock_get.call_args.kwargs["params"]["author"] == "Herbert"

    def test_skips_docs_without_cover(self):
        resp = self._mock_response(
            [
                {"key": "/works/X"},
                {"key": "/works/Y", "cover_i": 99},
            ]
        )
        with patch("scripts.shelfie.requests.get", return_value=resp):
            assert _find_prod_cover_id("Hi") == 99

    def test_none_when_no_docs(self):
        resp = self._mock_response([])
        with patch("scripts.shelfie.requests.get", return_value=resp):
            assert _find_prod_cover_id("Hi") is None

    def test_none_when_no_doc_has_cover(self):
        resp = self._mock_response([{"key": "/works/X"}, {"key": "/works/Y"}])
        with patch("scripts.shelfie.requests.get", return_value=resp):
            assert _find_prod_cover_id("Hi") is None

    def test_none_on_http_error(self):
        with patch("scripts.shelfie.requests.get", side_effect=requests.RequestException):
            assert _find_prod_cover_id("Hi") is None

    def test_omits_author_param_when_empty(self):
        resp = self._mock_response([{"cover_i": 7}])
        with patch("scripts.shelfie.requests.get", return_value=resp) as mock_get:
            _find_prod_cover_id("Solo Title")
        assert "author" not in mock_get.call_args.kwargs["params"]


class TestCmdPopulateCovers:
    def test_patches_only_works_with_cover_matches(self):
        targets = [
            ("/works/OL1W", "Found Book", "A"),
            ("/works/OL2W", "Missing Book", "B"),
        ]

        def fake_find(title, author=""):
            return 42 if title == "Found Book" else None

        with (
            patch("scripts.shelfie._coverless_works_from_solr", return_value=targets),
            patch("scripts.shelfie._find_prod_cover_id", side_effect=fake_find),
            patch("scripts.shelfie._merge_save") as mock_save,
        ):
            cmd_populate_covers(ol=MagicMock())

        assert mock_save.call_count == 1
        (patches,) = mock_save.call_args[0]
        assert patches == [{"key": "/works/OL1W", "type": {"key": "/type/work"}, "covers": [42]}]

    def test_noop_when_no_coverless_works(self):
        with (
            patch("scripts.shelfie._coverless_works_from_solr", return_value=[]),
            patch("scripts.shelfie._find_prod_cover_id") as mock_find,
            patch("scripts.shelfie._merge_save") as mock_save,
        ):
            cmd_populate_covers(ol=MagicMock())
        mock_find.assert_not_called()
        mock_save.assert_not_called()

    def test_continues_after_save_error(self):
        targets = [
            ("/works/OL1W", "Book 1", "A"),
            ("/works/OL2W", "Book 2", "B"),
        ]

        def fake_save(patches, comment=""):
            if patches[0]["key"] == "/works/OL1W":
                raise requests.RequestException("boom")

        with (
            patch("scripts.shelfie._coverless_works_from_solr", return_value=targets),
            patch("scripts.shelfie._find_prod_cover_id", return_value=7),
            patch("scripts.shelfie._merge_save", side_effect=fake_save) as mock_save,
        ):
            cmd_populate_covers(ol=MagicMock())
        # Both works attempted even though the first raised.
        assert mock_save.call_count == 2


class TestGuessPassword:
    def test_admin_uses_default_login_password(self):
        assert _guess_password("admin") == "admin123"

    def test_openlibrary_uses_default_login_password(self):
        assert _guess_password("openlibrary") == "admin123"

    def test_unknown_username_returns_none(self):
        assert _guess_password("alice") is None
        assert _guess_password("") is None
        assert _guess_password("testuser_1") is None


class TestCmdListUsers:
    def test_lists_users_with_roles_and_password_hints(self, capsys):
        user_keys = ["/people/admin", "/people/bob", "/people/alice"]
        accounts = {
            "admin": {"email": "admin@example.com"},
            "bob": {"email": "bob@example.com"},
            "alice": {"email": "alice@example.com"},
        }
        roles = {
            "/people/admin": ["admin", "librarians"],
            "/people/bob": ["beta-testers"],
        }

        def find_account(username):
            return accounts.get(username)

        with (
            patch("scripts.shelfie._infobase_keys_of_type", return_value=user_keys),
            patch("scripts.shelfie._infobase_find_account", side_effect=find_account),
            patch("scripts.shelfie._get_user_roles_map", return_value=roles),
        ):
            cmd_list_users(ol=MagicMock())

        out = capsys.readouterr().out
        # Each user is listed with its email.
        assert "admin" in out
        assert "admin@example.com" in out
        assert "bob@example.com" in out
        assert "alice@example.com" in out
        # Bootstrap admin shows its default password hint; others show "(hashed)".
        assert "admin123" in out
        assert "(hashed)" in out
        # Roles are joined; users with no roles show "-".
        assert "admin, librarians" in out
        assert "beta-testers" in out
        # Footer reports the count.
        assert "3 user(s) found" in out

    def test_handles_missing_account_lookup(self, capsys):
        """If /account/find fails for a user, email falls back to empty."""
        with (
            patch("scripts.shelfie._infobase_keys_of_type", return_value=["/people/ghost"]),
            patch("scripts.shelfie._infobase_find_account", return_value=None),
            patch("scripts.shelfie._get_user_roles_map", return_value={}),
        ):
            cmd_list_users(ol=MagicMock())

        out = capsys.readouterr().out
        assert "ghost" in out
        assert "(hashed)" in out
        assert "1 user(s) found" in out

    def test_empty_when_no_users(self, capsys):
        with patch("scripts.shelfie._infobase_keys_of_type", return_value=[]):
            cmd_list_users(ol=MagicMock())
        assert "No users found." in capsys.readouterr().out
