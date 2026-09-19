"""`editions.opds_acquisitions` — the one field, in one format (#12844).

A caller used to have to read `providers` for the providers Open Library
synthesizes and something else for the ones harvested from a registered feed,
then reconcile two different shapes. This is both, as OPDS2 acquisition links,
from one field.

Weighted towards the rules that are invisible when they break: the precedence
between a harvested row and a synthesized one, the provider-name mapping the
dedupe depends on, and the failure paths.
"""

from typing import Final

import pytest
import web

from openlibrary.core.acquisitions import (
    MAX_ACQUISITIONS_PER_DOC,
    MAX_ROWS_PER_QUERY,
    Acquisition,
    _row_budget,
    feed_provider_name,
    opds_links_for_edition,
    provider_acquisition_as_opds,
)
from openlibrary.core.db import _get_db, get_db
from openlibrary.plugins.worksearch.schemes.works import WorkSearchScheme

ACQUISITIONS_DDL: Final = """
CREATE TABLE acquisitions (
    id integer primary key, work_id integer not null, edition_id integer not null,
    provider_name text not null, local_id text not null, data json not null,
    created timestamp default current_timestamp, updated timestamp default current_timestamp,
    UNIQUE (local_id, provider_name)
);
"""

BORROW_REL: Final = "http://opds-spec.org/acquisition/borrow"
BUY_REL: Final = "http://opds-spec.org/acquisition/buy"


@pytest.fixture
def acquisitions_db(tmp_path):
    """File-backed, not ``:memory:``, so the table survives a second connection."""
    web.config.db_parameters = {"dbn": "sqlite", "db": str(tmp_path / "acq.db")}
    _get_db.cache_clear()
    db = get_db()
    db.query("DROP TABLE IF EXISTS acquisitions;")
    db.query(ACQUISITIONS_DDL)
    yield db
    db.query("DROP TABLE IF EXISTS acquisitions;")
    _get_db.cache_clear()


def store(edition_id, provider_name, local_id, link, work_id=450063):
    Acquisition.upsert(
        work_id=work_id,
        edition_id=edition_id,
        provider_name=provider_name,
        local_id=local_id,
        data={"acquisitions": [{"access": "borrow", "url": link["href"], "link": link}]},
    )


class FakeProviderAcquisition:
    """Stands in for ``book_providers.Acquisition``."""

    def __init__(self, access="buy", fmt="web", price=None, url="https://x/buy", provider_name="standard_ebooks"):
        self.access, self.format, self.price, self.url, self.provider_name = access, fmt, price, url, provider_name


# ---------------------------------------------------------------------------
# The provider-name mapping the dedupe depends on
# ---------------------------------------------------------------------------


class TestProviderNameMapping:
    def test_gutenberg_is_mapped_to_the_registry_spelling(self):
        """`book_providers` says `gutenberg`; the feed registry says
        `project_gutenberg`, because a feed's provider_name is also its
        `identifiers` key and the import validator requires them to agree.
        Without the mapping the two look like different providers and an
        edition gets both a harvested acquisition and a synthesized duplicate.
        """
        assert feed_provider_name("gutenberg") == "project_gutenberg"

    def test_a_name_that_already_agrees_is_unchanged(self):
        assert feed_provider_name("betterworldbooks") == "betterworldbooks"

    def test_an_unknown_name_passes_through(self):
        assert feed_provider_name("standard_ebooks") == "standard_ebooks"

    def test_none_stays_none(self):
        assert feed_provider_name(None) is None


# ---------------------------------------------------------------------------
# Coercing a synthesized provider into OPDS2
# ---------------------------------------------------------------------------


class TestProviderCoercion:
    def test_becomes_an_opds2_acquisition_link(self):
        link = provider_acquisition_as_opds(FakeProviderAcquisition(access="buy", fmt="epub", url="https://x/b"))
        assert link["rel"] == BUY_REL
        assert link["href"] == "https://x/b"
        assert link["type"] == "application/epub+zip"

    def test_the_provider_name_is_mapped_not_copied(self):
        link = provider_acquisition_as_opds(FakeProviderAcquisition(provider_name="gutenberg"))
        assert link["provider_name"] == "project_gutenberg"

    def test_an_access_kind_with_no_opds_equivalent_is_dropped(self):
        """Better to omit than to invent a `rel` the spec does not define."""
        assert provider_acquisition_as_opds(FakeProviderAcquisition(access="mystery")) is None

    def test_an_acquisition_with_no_url_is_dropped(self):
        assert provider_acquisition_as_opds(FakeProviderAcquisition(url=None)) is None

    def test_a_string_price_is_not_passed_off_as_an_opds_price(self):
        """`providers` carries "$4.99"; OPDS2 wants a currency and a number.
        Parsing it would mean guessing, so it goes under a distinct key and
        nothing downstream can read a fabricated amount as `price`."""
        link = provider_acquisition_as_opds(FakeProviderAcquisition(price="$4.99"))
        assert link["properties"] == {"price_display": "$4.99"}
        assert "price" not in link["properties"]


# ---------------------------------------------------------------------------
# Reading the stored links
# ---------------------------------------------------------------------------


class TestStoredLinks:
    def test_returns_the_stored_opds_link_itself(self, acquisitions_db):
        """The blob keeps the provider's raw OPDS2 link as the source of truth,
        so it is returned rather than rebuilt."""
        store(36620178, "lenny", "36620178", {"rel": BORROW_REL, "href": "https://l/items/36620178/borrow", "type": "application/opds-publication+json"})
        links = opds_links_for_edition(Acquisition.get_by_editions([36620178])[36620178])
        assert links[0]["rel"] == BORROW_REL
        assert links[0]["type"] == "application/opds-publication+json"
        assert links[0]["provider_name"] == "lenny"

    def test_a_feed_cannot_relabel_itself(self, acquisitions_db):
        """`data` is written from an external feed, so the row's own
        provider_name is applied after the blob is spread."""
        store(36620178, "realprovider", "r-1", {"rel": BORROW_REL, "href": "https://l/x", "provider_name": "SPOOFED"})
        links = opds_links_for_edition(Acquisition.get_by_editions([36620178])[36620178])
        assert links[0]["provider_name"] == "realprovider"

    def test_a_row_with_an_unusable_blob_is_skipped_not_raised(self, acquisitions_db):
        """jsonb's top level can be a list; `.get` on it raises, and one bad
        feed record must not cost the page its acquisitions."""
        acquisitions_db.query(
            "INSERT INTO acquisitions (work_id, edition_id, provider_name, local_id, data) VALUES (450063, 36620178, 'broken', 'b-1', '[\"nope\"]')"
        )
        store(36620178, "lenny", "36620178", {"rel": BORROW_REL, "href": "https://l/good"})
        links = opds_links_for_edition(Acquisition.get_by_editions([36620178])[36620178])
        assert [link["provider_name"] for link in links] == ["lenny"]

    def test_an_entry_without_a_link_is_skipped(self, acquisitions_db):
        Acquisition.upsert(work_id=1, edition_id=2, provider_name="lenny", local_id="a", data={"acquisitions": [{"access": "borrow", "url": "https://x"}]})
        assert opds_links_for_edition(Acquisition.get_by_editions([2])[2]) == []

    def test_links_per_edition_are_capped(self, acquisitions_db):
        for i in range(MAX_ACQUISITIONS_PER_DOC + 10):
            store(36620178, f"p{i}", f"l{i}", {"rel": BORROW_REL, "href": f"https://x/{i}"})
        links = opds_links_for_edition(Acquisition.get_by_editions([36620178])[36620178])
        assert len(links) == MAX_ACQUISITIONS_PER_DOC

    def test_the_row_budget_is_absolutely_capped(self):
        assert _row_budget(1) == MAX_ACQUISITIONS_PER_DOC
        assert _row_budget(1_000_000) == MAX_ROWS_PER_QUERY


# ---------------------------------------------------------------------------
# Precedence: harvested wins, synthesized fills the gaps
# ---------------------------------------------------------------------------


class TestPrecedence:
    def _stitch(self, monkeypatch, solr_doc, provider_acquisitions, stored):
        monkeypatch.setattr("openlibrary.book_providers.get_acquisitions", lambda d, e: provider_acquisitions)
        return WorkSearchScheme._opds_acquisitions(solr_doc, object(), stored)

    def test_a_harvested_row_wins_over_the_synthesized_one(self, acquisitions_db, monkeypatch):
        """The feed is the provider's own statement of what it offers; the
        synthesized version is our inference."""
        store(
            36620178, "betterworldbooks", "isbn-1", {"rel": BUY_REL, "href": "https://bwb/harvested", "properties": {"price": {"currency": "USD", "value": 1.01}}}
        )
        stored = Acquisition.get_by_editions([36620178])
        links = self._stitch(
            monkeypatch, {"key": "/books/OL36620178M"}, [FakeProviderAcquisition(provider_name="betterworldbooks", url="https://bwb/synth")], stored
        )
        assert [link["href"] for link in links] == ["https://bwb/harvested"]

    def test_a_provider_with_no_harvested_row_is_appended(self, acquisitions_db, monkeypatch):
        store(36620178, "lenny", "36620178", {"rel": BORROW_REL, "href": "https://l/borrow"})
        stored = Acquisition.get_by_editions([36620178])
        links = self._stitch(
            monkeypatch, {"key": "/books/OL36620178M"}, [FakeProviderAcquisition(provider_name="standard_ebooks", url="https://se/read")], stored
        )
        assert sorted(link["provider_name"] for link in links) == ["lenny", "standard_ebooks"]

    def test_gutenberg_is_not_duplicated_across_the_two_sources(self, acquisitions_db, monkeypatch):
        """THE case the mapping exists for: the registry says
        `project_gutenberg`, `book_providers` says `gutenberg`. Comparing the
        raw names emits both."""
        store(36620178, "project_gutenberg", "1342", {"rel": "http://opds-spec.org/acquisition/open-access", "href": "https://g/1342.epub"})
        stored = Acquisition.get_by_editions([36620178])
        links = self._stitch(
            monkeypatch, {"key": "/books/OL36620178M"}, [FakeProviderAcquisition(access="open-access", provider_name="gutenberg", url="https://g/synth")], stored
        )
        assert [link["href"] for link in links] == ["https://g/1342.epub"]

    def test_an_edition_with_no_rows_still_gets_its_providers(self, acquisitions_db, monkeypatch):
        """The absence of a feed must be invisible to the caller."""
        links = self._stitch(monkeypatch, {"key": "/books/OL999M"}, [FakeProviderAcquisition(provider_name="standard_ebooks")], {})
        assert [link["provider_name"] for link in links] == ["standard_ebooks"]

    def test_an_unparseable_key_does_not_raise(self, acquisitions_db, monkeypatch):
        links = self._stitch(monkeypatch, {"key": "/books/OL"}, [FakeProviderAcquisition(provider_name="standard_ebooks")], {})
        assert [link["provider_name"] for link in links] == ["standard_ebooks"]


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class TestFieldRegistration:
    def test_registered_dotted_only_so_it_is_editions_only(self):
        """A bare name is expanded into both `work.X` and `editions.X`, which
        would call getattr(work, "opds_acquisitions"). A price belongs to a
        printing, not to a work."""
        assert "editions.opds_acquisitions" in WorkSearchScheme.non_solr_fields
        assert "opds_acquisitions" not in WorkSearchScheme.non_solr_fields

    def test_it_goes_through_the_repo_s_declared_mechanism(self):
        """Not a second post-processing convention bolted onto the search
        response -- the same `non_solr_fields` path `providers` uses."""
        assert "editions.providers" in WorkSearchScheme.non_solr_fields
