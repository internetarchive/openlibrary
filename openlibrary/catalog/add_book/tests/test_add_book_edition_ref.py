"""A record that names its Open Library edition should get that edition (#12844).

``build_pool`` matches on title, OCLC, LCCN, ocaid and ISBN, and ignores
``identifiers.*``. A provider feed whose records carry none of those -- only a
title, authors and a provider id -- is therefore pooled on title alone, against
however many same-title editions the catalog holds. For public-domain classics
that is thousands, and the failure is silent: a wrong-edition match returns
``success: true`` and attaches the provider's link to a book it does not hold.

Some feeds know the answer outright, because their own local id IS the edition
number. These tests cover honouring that, and the two ways honouring it naively
would go wrong: trusting an id that does not resolve, and honouring it only when
a title pool happens to be non-empty.
"""

import logging

import pytest

from openlibrary.catalog import add_book
from openlibrary.catalog.add_book import (
    build_pool,
    find_ol_edition_ref,
    find_quick_match,
    load,
    resolve_edition_ref,
)


@pytest.fixture
def ia_writeback(monkeypatch):
    """Prevent ia writeback from making live requests."""
    monkeypatch.setattr(add_book, "update_ia_metadata_for_ol_edition", lambda olid: {})


def _save_edition(mock_site, **fields):
    key = mock_site.new_key("/type/edition")
    mock_site.save({"key": key, "type": {"key": "/type/edition"}, **fields})
    return key


class TestFindOlEditionRef:
    def test_names_the_edition_it_carries(self):
        assert find_ol_edition_ref({"openlibrary": "OL51008637M"}) == "/books/OL51008637M"

    def test_absent_is_none(self):
        assert find_ol_edition_ref({"title": "test"}) is None

    def test_empty_is_none(self):
        assert find_ol_edition_ref({"openlibrary": ""}) is None


class TestResolveEditionRef:
    def test_existing_edition_resolves_to_itself(self, mock_site):
        key = _save_edition(mock_site, title="test")
        assert resolve_edition_ref(key) == key

    def test_missing_key_does_not_resolve(self, mock_site):
        assert resolve_edition_ref("/books/OL999999M") is None

    def test_redirect_resolves_to_its_target(self, mock_site):
        target = _save_edition(mock_site, title="test")
        mock_site.save({"key": "/books/OL77M", "type": {"key": "/type/redirect"}, "location": target})
        assert resolve_edition_ref("/books/OL77M") == target

    def test_non_edition_does_not_resolve(self, mock_site):
        mock_site.save({"key": "/works/OL1W", "type": {"key": "/type/work"}, "title": "test"})
        assert resolve_edition_ref("/works/OL1W") is None


class TestBuildPoolHonoursNamedEdition:
    def test_named_edition_narrows_the_pool_to_itself(self, mock_site):
        """Even with a same-title decoy present, the named edition is the pool.

        This is the whole point: the id is the answer, not a candidate to be
        weighed against title evidence.
        """
        named = _save_edition(mock_site, title="Frankenstein")
        decoy = _save_edition(mock_site, title="Frankenstein")
        pool = build_pool({"title": "Frankenstein", "openlibrary": named.split("/")[-1]})
        assert pool == {"openlibrary": [named]}
        assert decoy not in pool.get("title", [])

    def test_named_edition_wins_when_there_is_no_title_match_at_all(self, mock_site):
        """The empty-pool case, which is where the id matters most.

        ``_load`` returns ``load_data()`` immediately when ``build_pool`` comes
        back empty, so ``find_quick_match`` never runs. A record with no
        same-title match in the catalog -- an obscure local-history pamphlet,
        exactly the material a library-in-a-box feed carries -- would otherwise
        skip the shortcut and create a duplicate of the edition it just named.
        """
        named = _save_edition(mock_site, title="Proceedings of the Kirkwall Antiquarian Society")
        pool = build_pool({"title": "A title that matches nothing", "openlibrary": named.split("/")[-1]})
        assert pool == {"openlibrary": [named]}

    def test_dangling_id_falls_back_to_ordinary_matching(self, mock_site):
        """A typo'd id is a data-entry error, not a reason to stop matching.

        Lenny accepts the OL edition number as an unvalidated form field
        (ArchiveLabs/lenny#214), so a wrong id arrives looking exactly like a
        good one.
        """
        existing = _save_edition(mock_site, title="Dracula")
        pool = build_pool({"title": "Dracula", "openlibrary": "OL999999M"})
        assert "openlibrary" not in pool
        assert pool == {"title": [existing]}

    def test_record_without_a_named_edition_is_unaffected(self, mock_site):
        existing = _save_edition(mock_site, title="Dracula")
        assert build_pool({"title": "Dracula"}) == {"title": [existing]}


class TestFindQuickMatch:
    def test_returns_the_verified_edition(self, mock_site):
        named = _save_edition(mock_site, title="test")
        assert find_quick_match({"title": "test", "openlibrary": named.split("/")[-1]}) == named

    def test_follows_a_redirect_rather_than_returning_the_stale_key(self, mock_site):
        target = _save_edition(mock_site, title="test")
        mock_site.save({"key": "/books/OL77M", "type": {"key": "/type/redirect"}, "location": target})
        assert find_quick_match({"title": "test", "openlibrary": "OL77M"}) == target

    def test_dangling_id_falls_through_to_the_other_identifiers(self, mock_site):
        """Not a bare ``return "/books/" + rec["openlibrary"]``.

        That is what the code used to do, and ``_load`` then dereferences the
        result unconditionally -- ``site.get().get(match).authors`` raises on a
        key that is not there.
        """
        by_ocaid = _save_edition(mock_site, title="test", ocaid="testtest00test")
        rec = {"title": "test", "ocaid": "testtest00test", "openlibrary": "OL999999M"}
        assert find_quick_match(rec) == by_ocaid

    def test_dangling_id_with_nothing_else_to_go_on_is_no_match(self, mock_site):
        assert find_quick_match({"title": "test", "openlibrary": "OL999999M"}) is None


class TestLoadEndToEnd:
    def test_a_record_naming_an_edition_matches_that_edition_not_a_same_title_one(self, mock_site, add_languages, ia_writeback):
        first = load({"title": "Frankenstein", "source_records": ["test:001"], "authors": [{"name": "Mary Shelley"}]})
        second = load({"title": "Frankenstein", "source_records": ["test:002"], "authors": [{"name": "Mary Shelley"}]})
        # Two same-title editions exist; without the named id, matching picks one.
        target = second["edition"]["key"]
        assert first["edition"]["key"] != target

        reply = load(
            {
                "title": "Frankenstein",
                "source_records": ["lenny:3"],
                "authors": [{"name": "Mary Shelley"}],
                "identifiers": {"lenny": ["3"]},
                "openlibrary": target.split("/")[-1],
            }
        )
        assert reply["success"] is True
        assert reply["edition"]["key"] == target
        assert reply["edition"]["status"] != "created"

    def test_a_dangling_id_creates_rather_than_raising(self, mock_site, add_languages, ia_writeback):
        reply = load(
            {
                "title": "A title that matches nothing at all",
                "source_records": ["lenny:999999"],
                "authors": [{"name": "Nobody"}],
                "identifiers": {"lenny": ["999999"]},
                "openlibrary": "OL999999M",
            }
        )
        assert reply["success"] is True
        assert reply["edition"]["status"] == "created"

    def test_preview_does_not_write(self, mock_site, add_languages, ia_writeback):
        """``save=False`` must still resolve the named edition -- that is what
        the bookworm ``preview`` command relies on to measure matching
        before a feed is ever allowed to write."""
        created = load({"title": "Dracula", "source_records": ["test:001"], "authors": [{"name": "Bram Stoker"}]})
        target = created["edition"]["key"]
        before = len(list(mock_site.things({"type": "/type/edition"})))

        reply = load(
            {
                "title": "Dracula",
                "source_records": ["lenny:7"],
                "authors": [{"name": "Bram Stoker"}],
                "identifiers": {"lenny": ["7"]},
                "openlibrary": target.split("/")[-1],
            },
            save=False,
        )
        assert reply["edition"]["key"] == target
        assert reply.get("preview") is True
        assert len(list(mock_site.things({"type": "/type/edition"}))) == before


def test_a_dangling_id_is_logged_against_its_source(mock_site, caplog):
    """Trust in a provider's ids is decided per provider, not per record.

    So the warning has to name the source record: aggregating this line by
    source prefix is what makes "this instance's ids are unreliable" visible,
    and deactivating the feed is the response.
    """
    with caplog.at_level(logging.WARNING):
        build_pool({"title": "Dracula", "source_records": ["lenny:999999"], "openlibrary": "OL999999M"})
    assert "lenny:999999" in caplog.text
    assert "does not resolve to an edition" in caplog.text


class TestMalformedReferences:
    """A provider-supplied key can point at a record the catalog cannot follow.

    Broken redirects exist, and this reference is the one piece of an import
    record a third party controls outright, so each shape has to resolve to
    "no answer, match normally" rather than an exception inside ImportBot.

    These lock in behaviour rather than protect a guard: Infogami returns its
    falsy ``Nothing`` sentinel for a missing key instead of raising, so
    ``thing.location`` and ``thing.type.key`` chain harmlessly and the
    dereference is already safe. Verified by reverting the guard -- these tests
    pass either way, which is exactly why they are labelled as documentation.
    The one line that does work is the truthiness check on ``location``, which
    keeps a redirect with no location from issuing a lookup for an empty key.
    """

    def test_a_redirect_with_no_location_does_not_raise(self, mock_site):
        mock_site.save({"key": "/books/OL77M", "type": {"key": "/type/redirect"}})
        assert resolve_edition_ref("/books/OL77M") is None

    def test_a_redirect_pointing_at_nothing_does_not_raise(self, mock_site):
        mock_site.save({"key": "/books/OL77M", "type": {"key": "/type/redirect"}, "location": "/books/OL999999M"})
        assert resolve_edition_ref("/books/OL77M") is None

    def test_a_redirect_chain_is_not_followed_past_one_hop(self, mock_site):
        """One hop, deliberately: a cycle would otherwise hang the import."""
        target = _save_edition(mock_site, title="test")
        mock_site.save({"key": "/books/OL78M", "type": {"key": "/type/redirect"}, "location": target})
        mock_site.save({"key": "/books/OL77M", "type": {"key": "/type/redirect"}, "location": "/books/OL78M"})
        assert resolve_edition_ref("/books/OL77M") is None

    def test_an_already_prefixed_key_is_unresolvable_rather_than_fatal(self, mock_site):
        """`openlibrary` is documented as an OLID, but a caller passing a full
        key would previously build `/books//books/OL..M` and crash on it."""
        _save_edition(mock_site, title="test")
        assert find_ol_edition_ref({"openlibrary": "/books/OL1M"}) == "/books//books/OL1M"
        assert resolve_edition_ref("/books//books/OL1M") is None

    def test_a_record_with_a_malformed_reference_still_imports(self, mock_site, add_languages, ia_writeback):
        mock_site.save({"key": "/books/OL77M", "type": {"key": "/type/redirect"}})
        reply = load(
            {
                "title": "A malformed reference must not stop the import",
                "source_records": ["lenny:77"],
                "authors": [{"name": "Nobody"}],
                "openlibrary": "OL77M",
            }
        )
        assert reply["success"] is True
