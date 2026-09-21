"""`LennyProvider` — the entry that makes the existing Read/Borrow button offer Lenny (#13686).

Weighted towards the two things that are invisible when they break: that the
access kind comes from the harvested row rather than from the identifier, and
that a `borrow` acquisition actually renders a button. The template silently
emitted nothing for `borrow` before this, which for Lenny is half the catalogue
— 25 of the 50 publications in the live feed, counted 2026-09-20.
"""

from pathlib import Path
from typing import Final
from unittest.mock import patch

import pytest
import web
from web.template import Template

from openlibrary.book_providers import (
    PROVIDER_ORDER,
    EbookAccess,
    LennyProvider,
    get_book_provider,
)
from openlibrary.core.acquisitions import Acquisition as StoredAcquisition
from openlibrary.core.db import _get_db, get_db

ACQUISITIONS_DDL: Final = """
CREATE TABLE acquisitions (
    id integer primary key, work_id integer not null, edition_id integer not null,
    provider_name text not null, local_id text not null, data json not null,
    created timestamp default current_timestamp, updated timestamp default current_timestamp,
    UNIQUE (local_id, provider_name)
);
"""

# The two live endpoints, as the feed publishes them. They are not
# interchangeable: against the node on 2026-09-20, `/read` on a borrowable item
# answered 401 with an OPDS Authentication Document for `Accept: text/html` as
# well as for `*/*`, while `/borrow` answered 303 to the node's own sign-in.
READ_URL: Final = "https://lennyforlibraries.org/v1/api/items/37044817/read"
BORROW_URL: Final = "https://lennyforlibraries.org/v1/api/items/46539165/borrow"

lenny = LennyProvider()


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


def store(local_id: str, *entries: dict, provider_name: str = "lenny") -> None:
    """One harvested row, shaped the way ``add_book._save_acquisitions`` writes it."""
    StoredAcquisition.upsert(
        work_id=1,
        edition_id=int(local_id),
        provider_name=provider_name,
        local_id=local_id,
        data={"acquisitions": list(entries)},
    )


def edition(local_id: str = "46539165", **extra) -> dict:
    return {"key": f"/books/OL{local_id}M", "identifiers": {"lenny": [local_id]}, **extra}


class TestAccessComesFromTheHarvestedRow:
    """`identifiers.lenny` cannot tell a borrowable title from a free one.

    Both kinds carry exactly the same identifier, so a provider that
    synthesized a URL from it the way its neighbours do would be guessing, and
    would guess wrong for half the catalogue.
    """

    def test_borrow_row_yields_a_borrow_acquisition(self, acquisitions_db):
        store("46539165", {"access": "borrow", "url": BORROW_URL, "format": "application/opds-publication+json"})
        (acquisition,) = lenny.get_acquisitions(edition("46539165"))
        assert acquisition.access == "borrow"
        assert acquisition.url == BORROW_URL
        assert acquisition.provider_name == "lenny"

    def test_open_access_row_yields_an_open_access_acquisition(self, acquisitions_db):
        store("37044817", {"access": "open-access", "url": READ_URL, "format": "text/html"})
        (acquisition,) = lenny.get_acquisitions(edition("37044817"))
        assert acquisition.access == "open-access"
        assert acquisition.url == READ_URL

    def test_two_editions_with_the_same_shaped_identifier_differ(self, acquisitions_db):
        """The whole reason for the database read, in one assertion."""
        store("37044817", {"access": "open-access", "url": READ_URL})
        store("46539165", {"access": "borrow", "url": BORROW_URL})
        assert [a.access for a in lenny.get_acquisitions(edition("37044817"))] == ["open-access"]
        assert [a.access for a in lenny.get_acquisitions(edition("46539165"))] == ["borrow"]

    def test_format_is_web_for_the_borrow_link(self, acquisitions_db):
        """The stored mimetype describes the fulfillment, not the href.

        A borrow link's `indirectAcquisition` is an LCP license wrapping an
        epub; the URL itself is the node's HTML borrow page. Reporting `epub`
        would put a download icon on a link that opens a sign-in form.
        """
        store("46539165", {"access": "borrow", "url": BORROW_URL, "format": "application/epub+zip"})
        (acquisition,) = lenny.get_acquisitions(edition("46539165"))
        assert acquisition.format == "web"


class TestNothingToOffer:
    def test_no_row_yields_no_acquisitions(self, acquisitions_db):
        assert lenny.get_acquisitions(edition("46539165")) == []

    def test_another_providers_row_is_not_lennys(self, acquisitions_db):
        store("46539165", {"access": "borrow", "url": BORROW_URL}, provider_name="betterworldbooks")
        assert lenny.get_acquisitions(edition("46539165")) == []

    def test_a_database_failure_renders_no_button_rather_than_raising(self, acquisitions_db):
        """Both callers are places an exception cannot go: page rendering, and
        the Solr indexer, which need not have this database configured."""
        with patch.object(StoredAcquisition, "find_many", side_effect=OSError("no connection")):
            assert lenny.get_acquisitions(edition("46539165")) == []

    @pytest.mark.parametrize("url", ["javascript:alert(1)", "/v1/api/items/1/read", 42, None])
    def test_an_href_that_is_not_http_is_dropped(self, acquisitions_db, url):
        """`data` is authored by an external feed and a template renders it as
        an href, so it is attacker-controlled input checked on the way out."""
        store("46539165", {"access": "borrow", "url": url})
        assert lenny.get_acquisitions(edition("46539165")) == []

    def test_an_unknown_access_kind_is_dropped(self, acquisitions_db):
        store("46539165", {"access": "rent", "url": BORROW_URL})
        assert lenny.get_acquisitions(edition("46539165")) == []

    def test_a_row_whose_blob_is_not_a_list_is_skipped(self, acquisitions_db):
        StoredAcquisition.upsert(work_id=1, edition_id=46539165, provider_name="lenny", local_id="46539165", data={"acquisitions": "borrow"})
        assert lenny.get_acquisitions(edition("46539165")) == []


class TestEbookAccess:
    """`get_access` becomes Solr's `ebook_access`, which drives `public_scan_b`
    and `has_fulltext`. The base class answers PUBLIC unconditionally."""

    def test_a_borrowable_title_is_not_indexed_as_public(self, acquisitions_db):
        store("46539165", {"access": "borrow", "url": BORROW_URL})
        assert lenny.get_access(edition("46539165")) == EbookAccess.BORROWABLE

    def test_an_open_access_title_is_public(self, acquisitions_db):
        store("37044817", {"access": "open-access", "url": READ_URL})
        assert lenny.get_access(edition("37044817")) == EbookAccess.PUBLIC

    def test_nothing_stored_claims_nothing(self, acquisitions_db):
        """Including when the read failed: an unknown must not read as a free book."""
        assert lenny.get_access(edition("46539165")) == EbookAccess.NO_EBOOK


class TestProviderOrder:
    def test_lenny_is_registered(self):
        assert any(isinstance(provider, LennyProvider) for provider in PROVIDER_ORDER)

    def test_lenny_ranks_below_the_internet_archive(self):
        """Deliberate, and the reviewable decision in #13686.

        Of 50 publications sampled from the live feed on 2026-09-20, 21 of the
        25 borrowable ones are on an edition that already has an `ocaid`. Below
        IA those keep the button they render today; above IA all 21 would swap
        to a Lenny one.
        """
        names = [provider.short_name for provider in PROVIDER_ORDER]
        assert names.index("lenny") > names.index("ia")

    def test_an_edition_that_already_has_a_publisher_keeps_it(self, acquisitions_db):
        """25 of those 50 are open-access, and every one is a Standard Ebooks
        edition that already renders a Read button."""
        store("37044817", {"access": "open-access", "url": READ_URL})
        doc = edition("37044817")
        doc["identifiers"]["standard_ebooks"] = ["bram-stoker/dracula"]
        assert get_book_provider(doc).short_name == "standard_ebooks"

    def test_lenny_wins_when_nothing_else_offers_the_book(self, acquisitions_db):
        store("46539165", {"access": "borrow", "url": BORROW_URL})
        assert get_book_provider(edition("46539165")).short_name == "lenny"


class TestOneReadPerCall:
    """No caching, on purpose -- see `_harvested_lenny_entries`.

    A memo keyed on `web.ctx` outlives its request everywhere except web.py,
    and `TestNothingToOffer` is where that surfaces: an edition with no row
    answering with another edition's.
    """

    def test_every_call_reads_the_row(self, acquisitions_db):
        store("46539165", {"access": "borrow", "url": BORROW_URL})
        with patch.object(StoredAcquisition, "find_many", wraps=StoredAcquisition.find_many) as spy:
            lenny.get_acquisitions(edition("46539165"))
            lenny.get_acquisitions(edition("46539165"))
        assert spy.call_count == 2

    def test_a_row_deleted_mid_request_stops_being_offered(self, acquisitions_db):
        store("46539165", {"access": "borrow", "url": BORROW_URL})
        assert lenny.get_acquisitions(edition("46539165"))
        acquisitions_db.query("DELETE FROM acquisitions;")
        assert lenny.get_acquisitions(edition("46539165")) == []


class TestReadButtonTemplate:
    """The template had branches for `open-access` and `sample` only, so a
    `borrow` acquisition fell off the end of the chain and rendered an empty
    string -- a provider registered and a patron shown nothing."""

    @staticmethod
    def render(access: str, url: str) -> str:
        path = Path("openlibrary/templates/book_providers/read_button.html")
        template = Template(
            path.read_text(encoding="utf-8"),
            str(path),
            globals={"_": lambda text, *args: text % args if args else text},
        )
        acquisition = web.storage(access=access, url=url, format="web")
        return str(template("OL46539165M", acquisition, "Lenny", lambda action: f'data-ol-link-track="CTAClick|{action}"'))

    def test_a_borrow_acquisition_renders_a_button(self):
        html = self.render("borrow", BORROW_URL)
        assert "Borrow" in html
        assert 'href="/books/OL46539165M/-/borrow?action=borrow"' in html

    def test_the_borrow_button_does_not_link_straight_out_to_the_node(self):
        """`/-/borrow` is the href so #13688 has one place to land, and so the
        node URL is resolved server-side rather than published in the page.

        Asserts the button exists first. Without that the absence of the node
        URL is also true of the empty string this branch used to render, and
        the test would pass against the defect it is here to pin.
        """
        html = self.render("borrow", BORROW_URL)
        assert 'href="/books/OL46539165M/-/borrow?action=borrow"' in html
        assert BORROW_URL not in html

    def test_an_open_access_acquisition_still_renders_read(self):
        html = self.render("open-access", READ_URL)
        assert ">Read</a>" in html
        assert 'href="/books/OL46539165M/-/borrow?action=read"' in html
