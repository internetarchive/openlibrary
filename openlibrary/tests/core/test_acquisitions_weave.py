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

from openlibrary.book_providers import PROVIDER_ORDER
from openlibrary.book_providers import Acquisition as ProviderAcquisition
from openlibrary.core.acquisitions import (
    MAX_ACQUISITIONS_PER_DOC,
    MAX_EDITIONS_PER_QUERY,
    MAX_ROWS_PER_QUERY,
    Acquisition,
    _row_budget,
    _squash,
    feed_provider_name,
    opds_links_for_edition,
    provider_acquisition_as_opds,
    provider_dedupe_key,
)
from openlibrary.core.db import _get_db, get_db
from openlibrary.plugins.worksearch.schemes.works import WorkSearchScheme
from openlibrary.utils.request_context import site as site_var

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


def provider_acquisition(access="buy", fmt="web", price=None, url="https://x/buy", provider_name="standard_ebooks"):
    """A REAL ``book_providers.Acquisition``, not a duck-typed stand-in.

    The coercion reads five attributes off whatever `get_acquisitions` returns.
    A hand-rolled fake would keep passing if that dataclass renamed a field or
    changed a type, which is precisely the failure this suite exists to catch:
    a test tells you the code does what you wrote down, not that what you wrote
    down is the thing that runs.
    """
    return ProviderAcquisition(access=access, format=fmt, price=price, url=url, provider_name=provider_name)


# ---------------------------------------------------------------------------
# The provider-name mapping the dedupe depends on
# ---------------------------------------------------------------------------


class TestProviderNameMapping:
    """Both sides of the dedupe must agree on what a provider is called, or an
    edition shows two prices for one book.

    Resolved through `book_providers` rather than a hand-written dict. An
    earlier version was literally `{"gutenberg": "project_gutenberg"}`, which
    was redundant AND incomplete: `provider_name` already returns
    `identifier_key or short_name`, and `identifier_key` is the `identifiers.*`
    key -- exactly what a feed's provider_name must equal.
    """

    def test_a_short_name_resolves_to_the_registry_spelling(self):
        assert feed_provider_name("gutenberg") == "project_gutenberg"

    def test_every_provider_with_a_differing_key_resolves(self):
        """The hand-written dict knew about Gutenberg and missed Runeberg."""
        assert feed_provider_name("runeberg") == "project_runeberg"

    def test_a_display_name_resolves(self):
        """`BetterWorldBooksProvider.bwb_acquisitions` overwrites
        provider_name with "Better World Books", which
        `get_book_provider_by_name` does not resolve -- so matching on the
        registry alone still emitted a harvested AND a synthesized BWB
        acquisition for one edition."""
        assert feed_provider_name("Better World Books") == "betterworldbooks"
        assert feed_provider_name("Project Gutenberg") == "project_gutenberg"

    def test_a_name_that_already_agrees_is_unchanged(self):
        assert feed_provider_name("betterworldbooks") == "betterworldbooks"
        assert feed_provider_name("standard_ebooks") == "standard_ebooks"

    def test_a_provider_we_do_not_know_passes_through(self):
        """Feed-only providers (lenny) have no book_providers entry."""
        assert feed_provider_name("lenny") == "lenny"

    def test_none_stays_none(self):
        assert feed_provider_name(None) is None


# ---------------------------------------------------------------------------
# Coercing a synthesized provider into OPDS2
# ---------------------------------------------------------------------------


class TestProviderCoercion:
    def test_becomes_an_opds2_acquisition_link(self):
        link = provider_acquisition_as_opds(provider_acquisition(access="buy", fmt="epub", url="https://x/b"))
        assert link["rel"] == BUY_REL
        assert link["href"] == "https://x/b"
        assert link["type"] == "application/epub+zip"

    def test_the_provider_name_is_mapped_not_copied(self):
        link = provider_acquisition_as_opds(provider_acquisition(provider_name="gutenberg"))
        assert link["provider_name"] == "project_gutenberg"

    def test_an_access_kind_with_no_opds_equivalent_is_dropped(self):
        """Better to omit than to invent a `rel` the spec does not define."""
        assert provider_acquisition_as_opds(provider_acquisition(access="mystery")) is None

    def test_an_acquisition_with_no_url_is_dropped(self):
        assert provider_acquisition_as_opds(provider_acquisition(url=None)) is None

    def test_a_string_price_is_not_passed_off_as_an_opds_price(self):
        """`providers` carries "$4.99"; OPDS2 wants a currency and a number.
        Parsing it would mean guessing, so it goes under a distinct key and
        nothing downstream can read a fabricated amount as `price`."""
        link = provider_acquisition_as_opds(provider_acquisition(price="$4.99"))
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
            monkeypatch, {"key": "/books/OL36620178M"}, [provider_acquisition(provider_name="betterworldbooks", url="https://bwb/synth")], stored
        )
        assert [link["href"] for link in links] == ["https://bwb/harvested"]

    def test_a_provider_with_no_harvested_row_is_appended(self, acquisitions_db, monkeypatch):
        store(36620178, "lenny", "36620178", {"rel": BORROW_REL, "href": "https://l/borrow"})
        stored = Acquisition.get_by_editions([36620178])
        links = self._stitch(monkeypatch, {"key": "/books/OL36620178M"}, [provider_acquisition(provider_name="standard_ebooks", url="https://se/read")], stored)
        assert sorted(link["provider_name"] for link in links) == ["lenny", "standard_ebooks"]

    def test_bwb_is_not_duplicated_when_it_labels_itself_for_display(self, acquisitions_db, monkeypatch):
        """The second HIGH defect from independent review. `bwb_acquisitions`
        sets provider_name to "Better World Books"; the harvested row says
        "betterworldbooks". Without display-name resolution the edition shows
        the harvested price AND a synthesized one -- two prices, one book.

        Latent rather than live: BWB's get_acquisitions returns [] unless
        `bwb_test_holdings` is configured, and it is set on neither production
        nor testing (verified: `providers` is [] for this edition on both).
        """
        store(36620178, "betterworldbooks", "isbn-1", {"rel": BUY_REL, "href": "https://bwb/harvested"})
        stored = Acquisition.get_by_editions([36620178])
        links = self._stitch(
            monkeypatch, {"key": "/books/OL36620178M"}, [provider_acquisition(provider_name="Better World Books", url="https://bwb/synth")], stored
        )
        assert [link["href"] for link in links] == ["https://bwb/harvested"]

    def test_gutenberg_is_not_duplicated_across_the_two_sources(self, acquisitions_db, monkeypatch):
        """THE case the mapping exists for: the registry says
        `project_gutenberg`, `book_providers` says `gutenberg`. Comparing the
        raw names emits both."""
        store(36620178, "project_gutenberg", "1342", {"rel": "http://opds-spec.org/acquisition/open-access", "href": "https://g/1342.epub"})
        stored = Acquisition.get_by_editions([36620178])
        links = self._stitch(
            monkeypatch, {"key": "/books/OL36620178M"}, [provider_acquisition(access="open-access", provider_name="gutenberg", url="https://g/synth")], stored
        )
        assert [link["href"] for link in links] == ["https://g/1342.epub"]

    def test_an_edition_with_no_rows_still_gets_its_providers(self, acquisitions_db, monkeypatch):
        """The absence of a feed must be invisible to the caller."""
        links = self._stitch(monkeypatch, {"key": "/books/OL999M"}, [provider_acquisition(provider_name="standard_ebooks")], {})
        assert [link["provider_name"] for link in links] == ["standard_ebooks"]

    def test_an_unparseable_key_does_not_raise(self, acquisitions_db, monkeypatch):
        links = self._stitch(monkeypatch, {"key": "/books/OL"}, [provider_acquisition(provider_name="standard_ebooks")], {})
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


def test_no_two_providers_squash_to_the_same_key():
    """Squashing case and punctuation could make two providers collide, which
    would silently rewrite one provider's name into another's and either
    suppress a real acquisition or merge two different ones.

    Checked against the live registry rather than a fixed list, so a provider
    added later that collides fails here instead of in production.
    """

    seen: dict[str, str] = {}
    for provider in PROVIDER_ORDER:
        for spelling in (provider.short_name, provider.provider_name):
            if not spelling:
                continue
            key = _squash(spelling)
            assert seen.get(key, provider.provider_name) == provider.provider_name, f"{key!r} is claimed by two providers"
            seen[key] = provider.provider_name


@pytest.mark.parametrize("feed_name", ["lenny", "project_gutenberg", "betterworldbooks", "lenny_lennyforlibraries_org"])
def test_a_registered_feed_name_is_never_rewritten_into_another_provider(feed_name):
    """Resolution must be idempotent for names the feed registry actually uses.

    A feed's provider_name is also its `identifiers` key and its
    `source_records` prefix, so rewriting one would not merely mislabel an
    acquisition -- it would break the dedupe in the other direction.
    """
    assert feed_provider_name(feed_name) == feed_name


# ---------------------------------------------------------------------------
# Security: this serves externally-authored content through a public,
# unauthenticated API. A provider feed controls every value in `data`, and an
# acquisition link exists to be rendered as an anchor -- so an unvalidated
# href is Open Library republishing attacker-controlled script under its own
# name. Checked on the way OUT as well as in, because rows harvested before
# the check existed are already in the table.
# ---------------------------------------------------------------------------


class TestHostileFeedContent:
    @pytest.mark.parametrize(
        "href",
        [
            "javascript:alert(document.domain)",
            "JavaScript:alert(1)",  # scheme matching must be case-insensitive
            "data:text/html;base64,PHNjcmlwdD4=",
            "//evil.test/x",  # protocol-relative: inherits the consumer's scheme
            "ftp://evil.test/x",
            "",
        ],
    )
    def test_a_stored_link_with_an_unsafe_scheme_is_not_served(self, acquisitions_db, href):
        store(36620178, "lenny", "l-1", {"rel": BORROW_REL, "href": href})
        assert opds_links_for_edition(Acquisition.get_by_editions([36620178]).get(36620178) or []) == []

    def test_a_safe_link_alongside_an_unsafe_one_still_serves(self, acquisitions_db):
        store(36620178, "hostile", "h-1", {"rel": BORROW_REL, "href": "javascript:alert(1)"})
        store(36620178, "lenny", "l-1", {"rel": BORROW_REL, "href": "https://lenny/borrow"})
        links = opds_links_for_edition(Acquisition.get_by_editions([36620178])[36620178])
        assert [link["provider_name"] for link in links] == ["lenny"]

    def test_a_synthesized_acquisition_with_an_unsafe_url_is_dropped(self):
        assert provider_acquisition_as_opds(provider_acquisition(url="javascript:alert(1)")) is None

    def test_html_in_a_title_is_passed_through_unescaped(self, acquisitions_db):
        """Deliberate. This is a JSON API: escaping here would double-escape
        for every correct consumer, and the consumer is what has a rendering
        context. The href check exists because a URL is executable in a way a
        title is not."""
        store(36620178, "lenny", "l-1", {"rel": BORROW_REL, "href": "https://l/x", "title": "<img src=x onerror=alert(1)>"})
        links = opds_links_for_edition(Acquisition.get_by_editions([36620178])[36620178])
        assert links[0]["title"] == "<img src=x onerror=alert(1)>"


class TestPageSizeCannotChooseTheQuerySize:
    """`/search.json`'s `limit` has no upper bound — `Pagination.limit` is
    `ge=0` with no `le=`, and `limit=1200` really returns 1200 documents
    (verified against a live deployment). Without a cap here, an
    unauthenticated caller chooses the size of an `IN` query on the single
    connection every coroutine in the worker shares.
    """

    def test_the_lookup_is_capped_independent_of_page_size(self, acquisitions_db, monkeypatch, mock_site):
        site_var.set(mock_site)
        asked: dict = {}

        def capture(edition_ids):
            asked["n"] = len(edition_ids)
            return {}

        monkeypatch.setattr(
            "openlibrary.core.acquisitions.Acquisition.get_by_editions",
            staticmethod(capture),
        )
        huge = {"response": {"docs": [{"key": "/works/OL1W", "editions": {"docs": [{"key": f"/books/OL{i}M"} for i in range(1, 5001)]}}]}}
        WorkSearchScheme().add_non_solr_fields({"editions.opds_acquisitions"}, huge)
        assert asked["n"] == MAX_EDITIONS_PER_QUERY

    def test_an_ordinary_page_is_not_truncated(self, acquisitions_db, monkeypatch, mock_site):
        site_var.set(mock_site)
        asked: dict = {}

        def capture(edition_ids):
            asked["n"] = len(edition_ids)
            return {}

        monkeypatch.setattr(
            "openlibrary.core.acquisitions.Acquisition.get_by_editions",
            staticmethod(capture),
        )
        normal = {"response": {"docs": [{"key": "/works/OL1W", "editions": {"docs": [{"key": f"/books/OL{i}M"} for i in range(1, 101)]}}]}}
        WorkSearchScheme().add_non_solr_fields({"editions.opds_acquisitions"}, normal)
        assert asked["n"] == 100, "a default-sized page must be unaffected"


def test_the_field_is_actually_wired_into_add_non_solr_fields(acquisitions_db, mock_site, monkeypatch):
    """The integration point itself, which nothing else covers.

    Every precedence test calls `_opds_acquisitions` directly, so the whole
    dispatch could be deleted and the suite would stay green — a field that
    never appears in any response, shipped. Independent review found exactly
    that by mutation: removing the dispatch killed no test.

    This drives the real entry point instead, with a real edition Thing, so
    the wiring, the field-name match and the doc mutation are all exercised.
    """
    site_var.set(mock_site)
    mock_site.save({"key": "/books/OL77M", "type": {"key": "/type/edition"}, "title": "t"})
    store(77, "lenny", "l-77", {"rel": BORROW_REL, "href": "https://lenny/items/77/borrow"})
    monkeypatch.setattr("openlibrary.book_providers.get_acquisitions", lambda d, e: [])

    solr_result = {"response": {"docs": [{"key": "/works/OL1W", "editions": {"docs": [{"key": "/books/OL77M"}]}}]}}
    WorkSearchScheme().add_non_solr_fields({"editions.opds_acquisitions"}, solr_result)

    edition_doc = solr_result["response"]["docs"][0]["editions"]["docs"][0]
    assert edition_doc["opds_acquisitions"][0]["href"] == "https://lenny/items/77/borrow"
    assert edition_doc["opds_acquisitions"][0]["provider_name"] == "lenny"


class TestDefectsFoundByIndependentReview:
    """Each of these failed before its fix. All were found by review, not by me."""

    @pytest.mark.parametrize(
        ("harvested_name", "synthesized_name"),
        [
            ("gutenberg", "gutenberg"),
            ("Lenny", "lenny"),
            ("lenny", "Lenny"),
            ("Better World Books", "Better World Books"),
            ("standard-ebooks", "standard_ebooks"),
        ],
    )
    def test_dedupe_canonicalizes_both_sides(self, acquisitions_db, monkeypatch, harvested_name, synthesized_name):
        """Only the synthesized side used to be resolved, so the comparison was
        an exact match against a raw database string. Any harvested row not
        byte-identical to the provider's canonical name -- a capital letter was
        enough -- produced two prices for one book."""
        store(36620178, harvested_name, "h-1", {"rel": BUY_REL, "href": "https://harvested"})
        stored = Acquisition.get_by_editions([36620178])
        monkeypatch.setattr(
            "openlibrary.book_providers.get_acquisitions", lambda d, e: [provider_acquisition(provider_name=synthesized_name, url="https://synth")]
        )
        links = WorkSearchScheme._opds_acquisitions({"key": "/books/OL36620178M"}, object(), stored)
        assert [link["href"] for link in links] == ["https://harvested"]

    def test_the_dedupe_key_is_not_the_display_name(self):
        """A feed-only provider has no book_providers entry, so resolving for
        display leaves it alone -- which made the dedupe a case-sensitive exact
        match for exactly the providers that have harvested rows today."""
        assert feed_provider_name("Lenny") == "Lenny", "display keeps the feed's own spelling"
        assert provider_dedupe_key("Lenny") == provider_dedupe_key("lenny") == "lenny"

    @pytest.mark.parametrize("hostile", [{"a": 1}, 42, ["x"], None])
    def test_a_non_string_provider_name_does_not_crash_the_search(self, hostile):
        """`provider_name` reaches this from an edition's `providers` blob via
        from_json_safe, which does not validate types. An AttributeError here
        escaped as a 500 on every search page that edition appeared on."""
        assert feed_provider_name(hostile) is None
        assert provider_acquisition_as_opds(provider_acquisition(provider_name=hostile)) is not None

    def test_every_edition_on_a_page_gets_its_own_budget(self, acquisitions_db):
        """The cap used to be one global SQL LIMIT applied after ORDER BY, so
        on a large page the editions sorted last -- the highest ids, i.e. the
        newest -- silently got nothing while the first ones got everything."""
        for edition_id in range(1, 121):
            for n in range(3):
                store(edition_id, f"p{n}", f"l-{edition_id}-{n}", {"rel": BUY_REL, "href": f"https://x/{edition_id}/{n}"})
        grouped = Acquisition.get_by_editions(list(range(1, 121)))
        assert len(grouped) == 120, "no edition may be starved of its rows"
        assert {len(rows) for rows in grouped.values()} == {3}


def test_one_greedy_edition_does_not_consume_another_edition_s_budget(acquisitions_db):
    """The cap is per edition. A single edition with more rows than the cap is
    truncated to it, and every other edition on the page still gets its own —
    the starvation the global SQL LIMIT used to cause."""
    for n in range(MAX_ACQUISITIONS_PER_DOC + 15):
        store(1, f"p{n:03d}", f"greedy-{n}", {"rel": BUY_REL, "href": f"https://x/1/{n}"})
    store(2, "lenny", "modest", {"rel": BORROW_REL, "href": "https://x/2"})
    grouped = Acquisition.get_by_editions([1, 2])
    assert len(grouped[1]) == MAX_ACQUISITIONS_PER_DOC
    assert len(grouped[2]) == 1, "the modest edition is unaffected by the greedy one"
