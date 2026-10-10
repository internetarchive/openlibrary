"""`LennyProvider` — the entry that makes the existing Read/Borrow button offer Lenny (#13686).

Weighted towards the two things that are invisible when they break: that the
access kind comes from the harvested row rather than from the identifier, and
that a `borrow` acquisition actually renders a button. The template silently
emitted nothing for `borrow` before this, which for Lenny is half the catalogue
— 25 of the 50 publications in the live feed, counted 2026-09-20.
"""

import logging
from pathlib import Path
from typing import Final
from unittest.mock import patch

import pytest
import web
from web.template import Template

from openlibrary import book_providers
from openlibrary.book_providers import (
    PROVIDER_ORDER,
    Acquisition,
    AcquisitionAccessLiteral,
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
    def render(
        access: AcquisitionAccessLiteral,
        url: str,
        provider_name: str | None = "lenny",
        provider_loan: dict | None = None,
    ) -> str:
        path = Path("openlibrary/templates/book_providers/read_button.html")
        template = Template(
            path.read_text(encoding="utf-8"),
            str(path),
            globals={"_": lambda text, *args: text % args if args else text},
        )
        # The real dataclass, not a `web.storage` of the fields this template
        # happens to read today. A stub silently omitting one raises
        # `AttributeError` the moment the template reads it, which reports as
        # the template being broken.
        acquisition = Acquisition(access=access, format="web", price=None, url=url, provider_name=provider_name)
        return str(
            template(
                "OL46539165M",
                acquisition,
                "Lenny",
                lambda action: f'data-ol-link-track="CTAClick|{action}"',
                provider_loan=provider_loan,
            )
        )

    def test_a_held_loan_offers_read_in_its_own_window(self):
        """Already true when this was written, and pinned rather than fixed:
        of the three places Open Library renders a Lenny reader link, this is
        the one that was right. The audit that found the other two is in the
        #13865 PR body; the point of this test is that the count stays at
        three and the right answer stays the right answer.
        """
        html = self.render("borrow", BORROW_URL, provider_loan={"read_url": READ_URL})
        assert f'href="{READ_URL}"' in html
        assert 'target="_blank"' in html
        assert "noopener" in html

    def test_a_borrow_acquisition_renders_a_button(self):
        html = self.render("borrow", BORROW_URL)
        assert "Borrow" in html
        assert 'href="/books/OL46539165M/-/borrow?action=borrow"' in html

    def test_the_borrow_button_does_not_link_straight_out_to_the_node(self):
        """`/-/borrow` is the href so #13688 has one place to land, and so the
        node URL is resolved server-side rather than published in the page.

        Asserts the button exists first, and that ordering is the point. The
        absence of the node URL is also true of the empty string this branch
        used to render, so without the first assertion this test passes against
        the exact defect it is here to pin -- observed, not hypothesised:
        written without it, it stayed green against the unfixed template while
        every other test in this class went red. An assertion satisfied by
        absence needs a companion that fails when nothing is rendered at all.
        """
        html = self.render("borrow", BORROW_URL)
        assert 'href="/books/OL46539165M/-/borrow?action=borrow"' in html
        assert BORROW_URL not in html

    def test_an_open_access_acquisition_still_renders_read(self):
        html = self.render("open-access", READ_URL)
        # master's #13721 ("Button label audit") moved every CTA label into a
        # `cta-btn__label` span, so a bare `>Read</a>` no longer matches.
        assert '<span class="cta-btn__label">Read</span>' in html
        assert 'href="/books/OL46539165M/-/borrow?action=read"' in html

    def test_the_borrow_button_says_which_provider_the_offer_came_from(self):
        """`provider_borrow_popup.js` selects on this to decide whether the
        borrow opens in a popup (#13688). Without the attribute the popup
        never opens and the patron leaves Open Library instead -- a silent
        regression, because the anchor still works."""
        html = self.render("borrow", BORROW_URL)
        assert ">Borrow</a>" in html
        assert 'data-ol-provider="lenny"' in html

    def test_a_borrow_button_with_no_provider_name_still_renders(self):
        """`Acquisition.provider_name` is optional, and an edit-book
        `providers` entry need not carry one. An empty attribute matches no
        entry in the module's allow-list, so the button keeps its plain
        behaviour rather than raising here."""
        html = self.render("borrow", BORROW_URL, provider_name=None)
        assert ">Borrow</a>" in html
        assert 'data-ol-provider=""' in html


@pytest.fixture
def one_scan_allowed():
    """Clear the process-wide scan throttle, so a test gets exactly one scan.

    ``setattr`` rather than an assignment on the imported name, so that these
    tests still reach their assertions -- and fail on "nothing was logged" --
    when run against source that has no throttle at all. A red that says
    `AttributeError` proves only that a symbol is missing.
    """
    book_providers._lenny_provider_scan_deadline = 0.0
    yield
    book_providers._lenny_provider_scan_deadline = 0.0


def lenny_warnings(caplog) -> list[str]:
    return [record.getMessage() for record in caplog.records if record.levelno >= logging.WARNING and record.name == "openlibrary.book_providers"]


class TestASecondNodeIsAudible:
    """Lenny names a node after its host once there is more than one of them,
    and this code reads exactly one name. Nothing here fixes that -- the
    button still vanishes -- it just stops the vanishing being silent.

    The failure cannot be caught by watching our own deploys, because the
    thing that triggers it is a library elsewhere standing up a node.
    """

    def test_a_row_no_configured_node_can_serve_is_named_in_the_log(self, acquisitions_db, one_scan_allowed, caplog):
        store("46539165", {"access": "borrow", "url": BORROW_URL}, provider_name="lenny_localhost")
        with caplog.at_level(logging.WARNING, logger="openlibrary.book_providers"):
            assert lenny.get_acquisitions(edition("46539165")) == []
        (warning,) = lenny_warnings(caplog)
        assert "lenny_localhost" in warning

    def test_the_healthy_single_node_case_says_nothing(self, acquisitions_db, one_scan_allowed, caplog):
        """Production is 94 works and every one is plain `lenny`. A warning
        that fires there is a warning nobody reads anywhere else."""
        store("46539165", {"access": "borrow", "url": BORROW_URL})
        store("37044817", {"access": "open-access", "url": READ_URL})
        with caplog.at_level(logging.WARNING, logger="openlibrary.book_providers"):
            assert len(lenny.get_acquisitions(edition("46539165"))) == 1
        assert lenny_warnings(caplog) == []

    def test_an_empty_table_says_nothing(self, acquisitions_db, one_scan_allowed, caplog):
        with caplog.at_level(logging.WARNING, logger="openlibrary.book_providers"):
            assert lenny.get_acquisitions(edition("46539165")) == []
        assert lenny_warnings(caplog) == []

    def test_it_fires_on_a_call_that_itself_succeeded(self, acquisitions_db, one_scan_allowed, caplog):
        """The whole design, in one assertion.

        An edition harvested under `lenny_localhost` carries
        `identifiers.lenny_localhost`, so `get_book_providers` never selects
        `LennyProvider` for it and `_harvested_lenny_entries` is never called
        on its behalf. Every call that does arrive is a healthy one. Gate the
        scan on the call having come up empty -- the obvious shape -- and this
        goes quiet in exactly the situation it exists for.
        """
        store("46539165", {"access": "borrow", "url": BORROW_URL})
        store("99999999", {"access": "borrow", "url": BORROW_URL}, provider_name="lenny_localhost")
        with caplog.at_level(logging.WARNING, logger="openlibrary.book_providers"):
            acquisitions = lenny.get_acquisitions(edition("46539165"))
        assert len(acquisitions) == 1, "the healthy edition must still render its button"
        (warning,) = lenny_warnings(caplog)
        assert "lenny_localhost" in warning

    def test_a_provider_that_merely_sorts_next_to_lenny_is_not_claimed(self, acquisitions_db, one_scan_allowed, caplog):
        """`lennylibrary` is not a Lenny node. Only `lenny` and `lenny_<host>`
        are names this scheme can produce."""
        store("46539165", {"access": "borrow", "url": BORROW_URL}, provider_name="lennylibrary")
        store("46539166", {"access": "borrow", "url": BORROW_URL}, provider_name="betterworldbooks")
        with caplog.at_level(logging.WARNING, logger="openlibrary.book_providers"):
            lenny.get_acquisitions(edition("46539165"))
        assert lenny_warnings(caplog) == []

    def test_every_unservable_node_is_named_not_just_the_first(self, acquisitions_db, one_scan_allowed, caplog):
        """A report that names one of three is how the other two ship."""
        store("1", {"access": "borrow", "url": BORROW_URL}, provider_name="lenny_b_example_org")
        store("2", {"access": "borrow", "url": BORROW_URL}, provider_name="lenny_a_example_org")
        store("3", {"access": "borrow", "url": BORROW_URL}, provider_name="lenny_c_example_org")
        with caplog.at_level(logging.WARNING, logger="openlibrary.book_providers"):
            lenny.get_acquisitions(edition("46539165"))
        (warning,) = lenny_warnings(caplog)
        for host in ("lenny_a_example_org", "lenny_b_example_org", "lenny_c_example_org"):
            assert host in warning


class TestItCannotSpamAHotPath:
    """`_harvested_lenny_entries` runs once per Lenny edition per page render,
    and the scan behind this warning is unindexed -- `acquisitions` is indexed
    on work_id, edition_id and updated, not provider_name."""

    def test_a_page_of_many_lenny_editions_logs_once(self, acquisitions_db, one_scan_allowed, caplog):
        store("46539165", {"access": "borrow", "url": BORROW_URL}, provider_name="lenny_localhost")
        with caplog.at_level(logging.WARNING, logger="openlibrary.book_providers"):
            for _ in range(25):
                lenny.get_acquisitions(edition("46539165"))
        assert len(lenny_warnings(caplog)) == 1

    def test_a_page_of_many_lenny_editions_scans_once(self, acquisitions_db, one_scan_allowed):
        """The log line is deduplicated because the query is, not the other
        way round: the cost this is bounding is the read, not the message."""
        store("46539165", {"access": "borrow", "url": BORROW_URL}, provider_name="lenny_localhost")
        with patch.object(StoredAcquisition, "distinct_provider_names", wraps=StoredAcquisition.distinct_provider_names) as spy:
            for _ in range(25):
                lenny.get_acquisitions(edition("46539165"))
        assert spy.call_count == 1

    def test_a_failing_scan_is_not_retried_by_the_rest_of_the_page(self, acquisitions_db, one_scan_allowed):
        """The deadline moves before the query, not after, so a scan that
        raises or hangs costs the page once rather than once per edition."""
        with patch.object(StoredAcquisition, "distinct_provider_names", side_effect=OSError("boom")) as failing:
            for _ in range(25):
                lenny.get_acquisitions(edition("46539165"))
        assert failing.call_count == 1

    def test_nothing_is_scanned_when_the_database_did_not_answer(self, acquisitions_db, one_scan_allowed):
        """The Solr indexer need not have this database configured at all."""
        with (
            patch.object(StoredAcquisition, "find_many", side_effect=OSError("no connection")),
            patch.object(StoredAcquisition, "distinct_provider_names") as scan,
        ):
            assert lenny.get_acquisitions(edition("46539165")) == []
        scan.assert_not_called()


class TestTheWarningChangesNothing:
    """This function's contract is that it returns `[]` on any failure: both
    callers are places an exception cannot go."""

    def test_a_scan_that_raises_does_not_reach_the_caller(self, acquisitions_db, one_scan_allowed, caplog):
        store("46539165", {"access": "borrow", "url": BORROW_URL})
        with (
            caplog.at_level(logging.WARNING, logger="openlibrary.book_providers"),
            patch.object(StoredAcquisition, "distinct_provider_names", side_effect=OSError("boom")),
        ):
            (acquisition,) = lenny.get_acquisitions(edition("46539165"))
        assert acquisition.url == BORROW_URL
        assert lenny_warnings(caplog) == []

    def test_an_unservable_row_does_not_change_what_is_offered(self, acquisitions_db, one_scan_allowed, caplog):
        store("46539165", {"access": "borrow", "url": BORROW_URL})
        store("46539165", {"access": "open-access", "url": READ_URL}, provider_name="lenny_localhost")
        with caplog.at_level(logging.WARNING, logger="openlibrary.book_providers"):
            assert lenny.get_access(edition("46539165")) == EbookAccess.BORROWABLE
        assert len(lenny_warnings(caplog)) == 1
