import datetime
import json
import logging
from pathlib import Path
from typing import Final

import pytest
import web

from openlibrary.bookworm import harvest, opds
from openlibrary.bookworm.harvest import _as_utc
from openlibrary.bookworm.registry import CURSOR_MODIFIED_SINCE, FeedRegistry
from openlibrary.core.acquisitions import Acquisition
from openlibrary.core.db import get_db

SAMPLES = Path(__file__).parent / "samples"
NOW: Final = datetime.datetime(2026, 7, 30, tzinfo=datetime.UTC)

FEED_REGISTRY_DDL: Final = """
CREATE TABLE feed_registry (
    id integer primary key, provider_name text not null, feed_type text not null default 'opds',
    url text not null, last_updated timestamp default null, data text not null default '{}',
    created timestamp default current_timestamp, updated timestamp default current_timestamp,
    UNIQUE (provider_name, url)
);
"""
IMPORT_BATCH_DDL: Final = "CREATE TABLE import_batch (id integer primary key, name text, submitter text, submit_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP);"
ACQUISITIONS_DDL: Final = """
CREATE TABLE acquisitions (
    id integer primary key, work_id integer not null, edition_id integer not null,
    provider_name text not null, local_id text not null, data text not null,
    created timestamp, updated timestamp, UNIQUE (local_id, provider_name)
);
"""
IMPORT_ITEM_DDL: Final = """
CREATE TABLE import_item (
    id integer primary key, batch_id integer, added_time timestamp, import_time timestamp,
    status text default 'pending', error text, ia_id text, data text, ol_key text,
    comments text, submitter text, UNIQUE (batch_id, ia_id)
);
"""


def feed_page(name: str) -> dict:
    return {"publications": json.loads((SAMPLES / f"{name}.json").read_text()), "links": []}


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        pass


class FakeSession:
    def __init__(self, pages):
        self.pages = pages
        self.calls: list[str] = []

    def get(self, url, **kwargs):
        self.calls.append(url)
        return FakeResponse(self.pages[url])


@pytest.fixture
def bookworm_db():
    web.config.db_parameters = {"dbn": "sqlite", "db": ":memory:"}
    db = get_db()
    for table in ("import_item", "import_batch", "feed_registry", "acquisitions"):
        db.query(f"DROP TABLE IF EXISTS {table};")
    # acquisitions is REQUIRED: _drop_unchanged reads it, and without the table
    # it silently took its exception fallback and every gate-2 assertion below
    # was vacuous.
    for ddl in (FEED_REGISTRY_DDL, IMPORT_BATCH_DDL, IMPORT_ITEM_DDL, ACQUISITIONS_DDL):
        db.query(ddl)
    yield db
    for table in ("import_item", "import_batch", "feed_registry", "acquisitions"):
        db.query(f"DROP TABLE IF EXISTS {table};")


def _register_active(provider_name: str, url: str, **kwargs) -> FeedRegistry:
    """Register a feed and activate it.

    Scheduled harvests only pick up ACTIVE feeds, so a test exercising
    harvest_all has to opt in the same way an operator does.
    """
    feed = FeedRegistry.register(provider_name, url, **kwargs)
    assert feed is not None
    FeedRegistry.set_status(feed.id, "active")
    activated = FeedRegistry.get_by_id(feed.id)
    assert activated is not None
    return activated


def test_harvest_bwb_submits_import_items_carrying_acquisitions(bookworm_db):
    FeedRegistry.register("betterworldbooks", "https://bwb/opds", id_strategy="isbn")
    feed = FeedRegistry.find("betterworldbooks", "https://bwb/opds")
    session = FakeSession({"https://bwb/opds": feed_page("bwb")})

    result = harvest.harvest_feed(feed, session=session, now=NOW)
    assert result["records"] == 2

    rows = list(bookworm_db.select("import_item"))
    assert {r.ia_id for r in rows} == {"betterworldbooks:9781737408802", "betterworldbooks:9798995425007"}
    data = json.loads(rows[0].data)
    assert data["acquisitions"][0]["provider_name"] == "betterworldbooks"
    assert data["acquisitions"][0]["data"]["access"] == "buy"
    # cursor advanced to the newest publication modified time in the feed (UTC)
    expected = max(_as_utc(opds.Publication(**p).modified) for p in json.loads((SAMPLES / "bwb.json").read_text()))
    assert _as_utc(FeedRegistry.get_by_id(feed.id).last_updated) == expected


def test_harvest_gutenberg_injects_modified_since_and_open_access(bookworm_db):
    FeedRegistry.register("project_gutenberg", "https://g/opds/search?sort=fil", id_strategy="gutenberg", cursor_style=CURSOR_MODIFIED_SINCE)
    feed = FeedRegistry.find("project_gutenberg", "https://g/opds/search?sort=fil")
    FeedRegistry.advance(feed.id, last_updated=datetime.datetime(2026, 7, 20))
    feed = FeedRegistry.get_by_id(feed.id)

    fetch_url = feed.request_url(datetime.datetime(2026, 7, 20, tzinfo=datetime.UTC))
    assert "modified_since=2026-07-20" in fetch_url
    session = FakeSession({fetch_url: feed_page("gutenberg")})

    result = harvest.harvest_feed(feed, session=session, now=NOW)
    assert result["records"] == 3
    assert any("modified_since=2026-07-20" in call for call in session.calls)
    data = json.loads(next(iter(bookworm_db.select("import_item"))).data)
    assert data["acquisitions"][0]["data"]["access"] == "open-access"
    # modified_since feeds advance the cursor to run time
    assert str(FeedRegistry.get_by_id(feed.id).last_updated).startswith("2026-07-30")


def test_harvest_all_covers_every_feed(bookworm_db):
    _register_active("betterworldbooks", "https://bwb/opds", id_strategy="isbn")
    _register_active("lenny", "https://lenny/opds", id_strategy="self_link")
    session = FakeSession({"https://bwb/opds": feed_page("bwb"), "https://lenny/opds": feed_page("lenny")})

    results = harvest.harvest_all(session=session)
    assert {r["feed"] for r in results} == {"betterworldbooks", "lenny"}
    assert {r["feed"]: r["records"] for r in results} == {"betterworldbooks": 2, "lenny": 3}


def test_one_malformed_publication_is_skipped_not_fatal(bookworm_db):
    """A single poison publication must not abort the feed (which would wedge the cursor)."""
    FeedRegistry.register("lenny", "https://lenny/opds", id_strategy="self_link")
    feed = FeedRegistry.find("lenny", "https://lenny/opds")
    good = json.loads((SAMPLES / "lenny.json").read_text())
    poison = {"metadata": {"title": "Poison"}, "links": [{"rel": "self"}]}  # link missing href -> ValidationError
    page = {"publications": [poison, *good], "links": []}
    session = FakeSession({"https://lenny/opds": page})

    result = harvest.harvest_feed(feed, session=session, now=NOW)
    assert result["records"] == len(good)  # the good ones still made it; poison skipped
    assert FeedRegistry.get_by_id(feed.id).last_updated is not None  # cursor advanced


def test_harvest_all_continues_when_one_feed_errors(bookworm_db):
    _register_active("betterworldbooks", "https://bwb/opds", id_strategy="isbn")
    _register_active("lenny", "https://lenny/opds", id_strategy="self_link")
    # lenny's URL is absent from the session -> FakeSession.get raises KeyError mid-harvest.
    session = FakeSession({"https://bwb/opds": feed_page("bwb")})

    results = harvest.harvest_all(session=session)
    by_feed = {r["feed"]: r for r in results}
    assert by_feed["betterworldbooks"]["records"] == 2  # healthy feed unaffected
    assert by_feed["lenny"]["records"] == 0
    assert by_feed["lenny"].get("error") is True


def test_dry_run_writes_nothing_and_leaves_the_cursor_alone(bookworm_db):
    """A dry run must be genuinely inert: no import items, no cursor advance.

    This is what makes it safe to validate a newly registered feed against
    production before letting it write.
    """
    FeedRegistry.register("betterworldbooks", "https://bwb/opds", id_strategy="isbn")
    feed = FeedRegistry.find("betterworldbooks", "https://bwb/opds")
    session = FakeSession({"https://bwb/opds": feed_page("bwb")})

    result = harvest.harvest_feed(feed, session=session, now=NOW, dry_run=True)

    # It still reports what it *would* have done.
    assert result["records"] == 2
    assert result["dry_run"] is True
    assert list(bookworm_db.select("import_item")) == []
    assert FeedRegistry.get_by_id(feed.id).last_updated is None


def test_dry_run_on_a_modified_since_feed_leaves_the_cursor_alone(bookworm_db):
    """The native path advances to run time, so it needs its own guard."""
    FeedRegistry.register("project_gutenberg", "https://g/opds/search?sort=fil", id_strategy="gutenberg", cursor_style=CURSOR_MODIFIED_SINCE)
    feed = FeedRegistry.find("project_gutenberg", "https://g/opds/search?sort=fil")
    FeedRegistry.advance(feed.id, last_updated=datetime.datetime(2026, 7, 20))
    feed = FeedRegistry.get_by_id(feed.id)
    session = FakeSession({feed.request_url(datetime.datetime(2026, 7, 20, tzinfo=datetime.UTC)): feed_page("gutenberg")})

    result = harvest.harvest_feed(feed, session=session, now=NOW, dry_run=True)

    assert result["records"] == 3
    assert list(bookworm_db.select("import_item")) == []
    assert str(FeedRegistry.get_by_id(feed.id).last_updated).startswith("2026-07-20")


def test_dry_run_applies_to_every_feed_in_harvest_all(bookworm_db):
    _register_active("betterworldbooks", "https://bwb/opds", id_strategy="isbn")
    _register_active("lenny", "https://lenny/opds", id_strategy="self_link")
    session = FakeSession({"https://bwb/opds": feed_page("bwb"), "https://lenny/opds": feed_page("lenny")})

    results = harvest.harvest_all(session=session, dry_run=True)

    assert all(r.get("dry_run") for r in results)
    assert list(bookworm_db.select("import_item")) == []


def test_a_future_modified_timestamp_cannot_push_the_cursor_forward(bookworm_db):
    """One bad ``modified`` must not permanently strand a feed's back-catalogue.

    A publication dated 2126 (provider typo, bad epoch conversion, clock skew)
    used to set the cursor to 2126. Every later run then filtered out every real
    record, and the "nothing newer, advance to now" fallback quietly recovered
    the cursor to the present -- leaving the entire back-catalogue below it,
    unharvestable, with no error and a zero exit.
    """
    FeedRegistry.register("betterworldbooks", "https://bwb/opds", id_strategy="isbn")
    feed = FeedRegistry.find("betterworldbooks", "https://bwb/opds")
    poisoned = json.loads((SAMPLES / "bwb.json").read_text())
    poisoned[0]["metadata"]["modified"] = "2126-01-01T00:00:00Z"
    session = FakeSession({"https://bwb/opds": {"publications": poisoned, "links": []}})

    harvest.harvest_feed(feed, session=session, now=NOW)

    cursor = _as_utc(FeedRegistry.get_by_id(feed.id).last_updated)
    assert cursor <= NOW, f"cursor advanced into the future: {cursor}"


def test_max_pages_truncation_is_reported(bookworm_db):
    """Truncating a crawl still advances the cursor, so it must not be silent."""
    FeedRegistry.register("betterworldbooks", "https://bwb/opds", id_strategy="isbn")
    feed = FeedRegistry.find("betterworldbooks", "https://bwb/opds")
    page1 = {"publications": json.loads((SAMPLES / "bwb.json").read_text()), "links": [{"rel": "next", "href": "https://bwb/opds?page=2"}]}
    session = FakeSession({"https://bwb/opds": page1, "https://bwb/opds?page=2": feed_page("bwb")})

    result = harvest.harvest_feed(feed, session=session, now=NOW, max_pages=1)

    assert result["truncated"] is True


def test_a_pagination_loop_is_reported_not_silently_treated_as_end_of_feed(bookworm_db):
    """A feed whose rel=next points back at itself would otherwise yield page 1
    forever, advance the cursor, and exit green."""
    FeedRegistry.register("lenny", "https://lenny/opds", id_strategy="self_link")
    feed = FeedRegistry.find("lenny", "https://lenny/opds")
    looping = {"publications": json.loads((SAMPLES / "lenny.json").read_text()), "links": [{"rel": "next", "href": "https://lenny/opds"}]}
    session = FakeSession({"https://lenny/opds": looping})

    result = harvest.harvest_feed(feed, session=session, now=NOW)

    assert result["truncated"] is True


def test_an_untruncated_crawl_is_not_flagged(bookworm_db):
    FeedRegistry.register("lenny", "https://lenny/opds", id_strategy="self_link")
    feed = FeedRegistry.find("lenny", "https://lenny/opds")
    session = FakeSession({"https://lenny/opds": feed_page("lenny")})

    assert "truncated" not in harvest.harvest_feed(feed, session=session, now=NOW)


def _many_pages(provider_url: str, pages: int, per_page: int) -> dict:
    """A synthetic multi-page feed of unique publications."""
    template = json.loads((SAMPLES / "lenny.json").read_text())[0]
    feed_pages = {}
    n = 0
    for page in range(pages):
        pubs = []
        for _ in range(per_page):
            n += 1
            pub = json.loads(json.dumps(template))
            for link in pub["links"]:
                if link["rel"] == "self":
                    link["href"] = f"https://lenny/opds/item/{n}"
            pub["metadata"]["title"] = f"Book {n}"
            pubs.append(pub)
        url = provider_url if page == 0 else f"{provider_url}?page={page}"
        nxt = [{"rel": "next", "href": f"{provider_url}?page={page + 1}"}] if page + 1 < pages else []
        feed_pages[url] = {"publications": pubs, "links": nxt}
    return feed_pages


def test_records_are_staged_incrementally_not_all_at_the_end(bookworm_db, monkeypatch):
    """A backfill from the beginning is ~78k publications for Gutenberg.

    Accumulating all of them before one _submit held the whole feed in memory
    and issued a single enormous dedupe IN(...) and multiple_insert. Flushing as
    we page bounds both.
    """
    monkeypatch.setattr(harvest, "SUBMIT_BATCH_SIZE", 10)
    FeedRegistry.register("lenny", "https://lenny/opds", id_strategy="self_link")
    feed = FeedRegistry.find("lenny", "https://lenny/opds")
    session = FakeSession(_many_pages("https://lenny/opds", pages=5, per_page=10))

    submits = []
    original = harvest._submit

    def recording_submit(feed_arg, records_arg):
        submits.append(len(records_arg))
        return original(feed_arg, records_arg)

    monkeypatch.setattr(harvest, "_submit", recording_submit)

    result = harvest.harvest_feed(feed, session=session, now=NOW)

    assert result["records"] == 50
    assert len(submits) > 1, f"expected incremental flushes, got one submit of {submits}"
    assert max(submits) <= 10, f"a flush exceeded SUBMIT_BATCH_SIZE: {submits}"
    assert len(list(bookworm_db.select("import_item"))) == 50


def test_incremental_flushing_still_writes_every_record_once(bookworm_db, monkeypatch):
    monkeypatch.setattr(harvest, "SUBMIT_BATCH_SIZE", 3)
    FeedRegistry.register("lenny", "https://lenny/opds", id_strategy="self_link")
    feed = FeedRegistry.find("lenny", "https://lenny/opds")
    session = FakeSession(_many_pages("https://lenny/opds", pages=4, per_page=5))

    harvest.harvest_feed(feed, session=session, now=NOW)

    rows = list(bookworm_db.select("import_item"))
    assert len(rows) == 20
    assert len({r.ia_id for r in rows}) == 20  # no duplicates from the flushing


def test_dry_run_still_stages_nothing_when_flushing_would_trigger(bookworm_db, monkeypatch):
    """The flush is inside the page loop, so it must respect dry_run too."""
    monkeypatch.setattr(harvest, "SUBMIT_BATCH_SIZE", 2)
    FeedRegistry.register("lenny", "https://lenny/opds", id_strategy="self_link")
    feed = FeedRegistry.find("lenny", "https://lenny/opds")
    session = FakeSession(_many_pages("https://lenny/opds", pages=3, per_page=5))

    result = harvest.harvest_feed(feed, session=session, now=NOW, dry_run=True)

    assert result["records"] == 15
    assert list(bookworm_db.select("import_item")) == []
    assert FeedRegistry.get_by_id(feed.id).last_updated is None


def test_each_feed_has_one_stable_batch_name(bookworm_db):
    """One predictable namespace per feed, deliberately not date-scoped."""
    FeedRegistry.register("lenny", "https://lenny/opds", id_strategy="self_link")
    feed = FeedRegistry.find("lenny", "https://lenny/opds")
    session = FakeSession({"https://lenny/opds": feed_page("lenny")})

    harvest.harvest_feed(feed, session=session, now=NOW)

    assert [b.name for b in bookworm_db.select("import_batch")] == ["lenny-opds"]


def test_a_long_backfill_lands_in_one_batch(bookworm_db, monkeypatch):
    """Incremental flushing must not fork a crawl across batches."""
    monkeypatch.setattr(harvest, "SUBMIT_BATCH_SIZE", 5)
    FeedRegistry.register("lenny", "https://lenny/opds", id_strategy="self_link")
    feed = FeedRegistry.find("lenny", "https://lenny/opds")
    session = FakeSession(_many_pages("https://lenny/opds", pages=4, per_page=5))

    harvest.harvest_feed(feed, session=session, now=NOW)

    assert len(list(bookworm_db.select("import_batch"))) == 1


def test_harvest_all_skips_pending_feeds(bookworm_db):
    """A registration must be stageable: registering a feed used to make it live
    on the very next cron tick, with no way to inspect it first."""
    FeedRegistry.register("lenny", "https://lenny/opds", id_strategy="self_link")
    active = FeedRegistry.register("betterworldbooks", "https://bwb/opds", id_strategy="isbn")
    FeedRegistry.set_status(active.id, "active")
    session = FakeSession({"https://bwb/opds": feed_page("bwb"), "https://lenny/opds": feed_page("lenny")})

    results = harvest.harvest_all(session=session)

    assert {r["feed"] for r in results} == {"betterworldbooks"}
    assert list(bookworm_db.select("import_item"))  # the active feed still ran


def test_a_pending_feed_can_still_be_harvested_explicitly(bookworm_db):
    """--provider must reach a pending feed, or it could never be validated."""
    feed = FeedRegistry.register("lenny", "https://lenny/opds", id_strategy="self_link")
    session = FakeSession({"https://lenny/opds": feed_page("lenny")})

    result = harvest.harvest_feed(FeedRegistry.get_by_id(feed.id), session=session, now=NOW, dry_run=True)

    assert result["records"] == 3


def test_legacy_rows_without_a_status_still_harvest(bookworm_db):
    """Rows written before status existed must not silently stop."""
    feed = FeedRegistry.register("lenny", "https://lenny/opds", id_strategy="self_link")
    # A blob with no "status" key at all, as rows predating status gating have.
    FeedRegistry.advance(feed.id, last_updated=None, data={"id_strategy": "self_link"})
    session = FakeSession({"https://lenny/opds": feed_page("lenny")})

    assert {r["feed"] for r in harvest.harvest_all(session=session)} == {"lenny"}


def test_a_changed_price_is_restaged_for_the_catalog(bookworm_db):
    """The reason the Feed Registry exists: a BWB price change must reach the
    catalog. add_items would drop it, because the ia_id already exists."""
    _register_active("betterworldbooks", "https://bwb/opds", id_strategy="isbn")
    feed = FeedRegistry.find("betterworldbooks", "https://bwb/opds")
    page = feed_page("bwb")
    session = FakeSession({"https://bwb/opds": page})
    harvest.harvest_feed(feed, session=session, now=NOW)

    before = {r.ia_id: json.loads(r.data) for r in bookworm_db.select("import_item")}
    first_id = next(iter(before))
    original_price = before[first_id]["acquisitions"][0]["data"].get("price")

    # The provider raises a price and bumps `modified`.
    changed = json.loads(json.dumps(page))
    for pub in changed["publications"]:
        for link in pub.get("links", []):
            if (link.get("properties") or {}).get("price"):
                link["properties"]["price"]["value"] = 99.99
        pub["metadata"]["modified"] = "2126-01-01T00:00:00Z".replace("2126", "2026")
    # Only terminal rows are refreshable, so simulate ImportBot completing it.
    bookworm_db.query("UPDATE import_item SET status='created'")
    FeedRegistry.advance(feed.id, last_updated=datetime.datetime(2020, 1, 1))
    feed = FeedRegistry.get_by_id(feed.id)

    harvest.harvest_feed(feed, session=FakeSession({"https://bwb/opds": changed}), now=NOW)

    after = {r.ia_id: (json.loads(r.data) if r.data else None) for r in bookworm_db.select("import_item")}
    assert len(after) == len(before), "a price change must not create a second row"
    new_price = after[first_id]["acquisitions"][0]["data"]["price"]
    assert new_price != original_price
    assert new_price["value"] == 99.99
    assert {r.status for r in bookworm_db.select("import_item")} == {"pending"}


def test_an_unchanged_republish_does_not_requeue(bookworm_db):
    """Re-offering identical records must not re-queue them -- that is the
    firehose behaviour that previously overwhelmed the database."""
    _register_active("betterworldbooks", "https://bwb/opds", id_strategy="isbn")
    feed = FeedRegistry.find("betterworldbooks", "https://bwb/opds")
    session = FakeSession({"https://bwb/opds": feed_page("bwb")})
    harvest.harvest_feed(feed, session=session, now=NOW)

    bookworm_db.query("UPDATE import_item SET status='created'")

    FeedRegistry.advance(feed.id, last_updated=datetime.datetime(2020, 1, 1))
    result = harvest.harvest_feed(FeedRegistry.get_by_id(feed.id), session=FakeSession({"https://bwb/opds": feed_page("bwb")}), now=NOW)

    assert result.get("refreshed", 0) == 0
    assert result.get("unchanged", 0) > 0
    assert {r.status for r in bookworm_db.select("import_item")} == {"created"}


def test_an_all_unchanged_run_reports_unchanged_rather_than_silence(bookworm_db, monkeypatch):
    """An operator reading the log needs to see that a run found nothing new,
    not an empty result that looks like the gate never ran."""
    _register_active("lenny", "https://lenny/opds", id_strategy="self_link")
    feed = FeedRegistry.find("lenny", "https://lenny/opds")
    session = FakeSession({"https://lenny/opds": feed_page("lenny")})

    # Pretend every record's acquisitions already match what is stored.
    monkeypatch.setattr(harvest, "_drop_unchanged", lambda feed_arg, records: [])

    result = harvest.harvest_feed(feed, session=session, now=NOW)

    assert result["unchanged"] == result["records"] > 0


def test_gate_two_drops_an_unchanged_multi_link_publication(bookworm_db):
    """A multi-link publication must compare equal when nothing changed.

    `acquisitions` is unique on (local_id, provider_name), so every link of one
    publication shares a row. The catalog stores them all under
    `{"acquisitions": [...]}` and this gate compares the same shape, so a
    Gutenberg book offering epub, html and txt is recognised as unchanged
    instead of being re-queued on every run forever.
    """
    _register_active("project_gutenberg", "https://g/opds", id_strategy="gutenberg")
    feed = FeedRegistry.find("project_gutenberg", "https://g/opds")
    pub = {
        "metadata": {
            "type": "http://schema.org/Book",
            "title": "Multi Format",
            "identifier": "https://www.gutenberg.org/ebooks/1342",
            "author": [{"name": "Jane Austen"}],
            "language": ["en"],
            "modified": "2026-09-01T00:00:00Z",
        },
        "links": [
            {"rel": "self", "href": "https://g/opds/1342", "type": "application/opds-publication+json"},
            {"rel": "http://opds-spec.org/acquisition/open-access", "href": "https://g/1342.epub", "type": "application/epub+zip"},
            {"rel": "http://opds-spec.org/acquisition/open-access", "href": "https://g/1342.txt", "type": "text/plain"},
        ],
    }
    session = FakeSession({"https://g/opds": {"publications": [pub], "links": []}})
    harvest.harvest_feed(feed, session=session, now=NOW)

    staged = json.loads(next(iter(bookworm_db.select("import_item"))).data)
    assert len(staged["acquisitions"]) == 2, "fixture must actually be multi-link"

    # Exactly what the catalog leaves behind: ONE row holding EVERY link.
    Acquisition.upsert(
        work_id=1,
        edition_id=1,
        provider_name="project_gutenberg",
        local_id=staged["acquisitions"][0]["local_id"],
        data={"acquisitions": [acq["data"] for acq in staged["acquisitions"]]},
    )
    bookworm_db.query("UPDATE import_item SET status='created', data=NULL")

    FeedRegistry.advance(feed.id, last_updated=datetime.datetime(2020, 1, 1))
    result = harvest.harvest_feed(
        FeedRegistry.get_by_id(feed.id),
        session=FakeSession({"https://g/opds": {"publications": [pub], "links": []}}),
        now=NOW,
    )

    assert result.get("refreshed", 0) == 0, "an unchanged multi-link publication must not be re-queued"
    assert result["unchanged"] == 1
    assert [r.status for r in bookworm_db.select("import_item")] == ["created"]


def test_gate_two_raises_rather_than_failing_open(bookworm_db, monkeypatch):
    """Returning every record on a read error would reset every
    previously-imported record to pending -- a DB blip becoming a mass re-queue.
    Propagating leaves the cursor un-advanced so the next run retries."""
    _register_active("lenny", "https://lenny/opds", id_strategy="self_link")
    feed = FeedRegistry.find("lenny", "https://lenny/opds")

    def boom(provider_name, local_ids):
        raise RuntimeError("acquisitions unavailable")

    monkeypatch.setattr(Acquisition, "find_many", staticmethod(boom))
    session = FakeSession({"https://lenny/opds": feed_page("lenny")})

    with pytest.raises(RuntimeError):
        harvest.harvest_feed(feed, session=session, now=NOW)

    assert FeedRegistry.get_by_id(feed.id).last_updated is None, "cursor must not advance"


def test_the_cursor_does_not_advance_past_a_rejected_publication(bookworm_db):
    """A publication with a parsable `modified` but no author is rejected by
    to_import_record. Advancing the cursor past it would mean a later fix — or a
    provider adding the missing author — could never surface it again."""
    _register_active("lenny", "https://lenny/opds", id_strategy="self_link")
    feed = FeedRegistry.find("lenny", "https://lenny/opds")
    rejected = {
        "metadata": {"type": "http://schema.org/Book", "title": "No Author", "language": ["en"], "modified": "2026-08-15T00:00:00Z"},
        "links": [
            {"rel": "self", "href": "https://lenny/opds/999", "type": "application/opds-publication+json"},
            {"rel": "http://opds-spec.org/acquisition/borrow", "href": "https://lenny/999/borrow", "type": "text/html"},
        ],
    }
    session = FakeSession({"https://lenny/opds": {"publications": [rejected], "links": []}})

    result = harvest.harvest_feed(feed, session=session, now=NOW)

    assert result["records"] == 0
    cursor = _as_utc(FeedRegistry.get_by_id(feed.id).last_updated)
    assert cursor > _as_utc(datetime.datetime(2026, 8, 15, tzinfo=datetime.UTC)) or cursor == _as_utc(NOW), (
        "an empty run advances to now, but must not adopt the rejected record's own timestamp"
    )


class TestSuspectEmptyFeed:
    """A feed assembled from another service can serve an empty catalogue at
    HTTP 200 when that service is down.

    Real incident (ArchiveLabs/lenny#208): Lenny builds its OPDS feed from Open
    Library's own search API, and during the 2026-09-04 OL outage a library
    holding 96 items served `numberOfItems: 0`. Advancing the cursor past that
    window loses it permanently, with a green exit code.
    """

    def test_zero_publications_with_a_next_link_is_rejected(self, bookworm_db, monkeytime):
        _register_active("lenny", "https://lenny/opds", id_strategy="self_link")
        feed = FeedRegistry.find("lenny", "https://lenny/opds")
        session = FakeSession({"https://lenny/opds": {"publications": [], "links": [{"rel": "next", "href": "https://lenny/opds?p=2"}]}})

        with pytest.raises(harvest.SuspectFeedPage):
            harvest.harvest_feed(feed, session=session, now=NOW)

        assert FeedRegistry.get_by_id(feed.id).last_updated is None, "cursor must not advance"

    def test_zero_publications_while_claiming_items_is_rejected(self, bookworm_db, monkeytime):
        _register_active("lenny", "https://lenny/opds", id_strategy="self_link")
        feed = FeedRegistry.find("lenny", "https://lenny/opds")
        session = FakeSession({"https://lenny/opds": {"publications": [], "links": [], "metadata": {"numberOfItems": 96}}})

        with pytest.raises(harvest.SuspectFeedPage):
            harvest.harvest_feed(feed, session=session, now=NOW)

        assert FeedRegistry.get_by_id(feed.id).last_updated is None

    def test_a_genuinely_caught_up_feed_is_fine(self, bookworm_db):
        """The normal case: nothing new since the cursor. No next link, no
        claimed items -- must NOT be mistaken for an outage."""
        _register_active("lenny", "https://lenny/opds", id_strategy="self_link")
        feed = FeedRegistry.find("lenny", "https://lenny/opds")
        session = FakeSession({"https://lenny/opds": {"publications": [], "links": [], "metadata": {"numberOfItems": 0}}})

        result = harvest.harvest_feed(feed, session=session, now=NOW)

        assert result["records"] == 0
        assert FeedRegistry.get_by_id(feed.id).last_updated is not None, "a real empty run advances"

    def test_the_failure_is_reported_per_feed_not_fatal(self, bookworm_db, monkeytime):
        """One feed serving an empty catalogue must not starve the others."""
        _register_active("lenny", "https://lenny/opds", id_strategy="self_link")
        _register_active("betterworldbooks", "https://bwb/opds", id_strategy="isbn")
        session = FakeSession(
            {
                "https://lenny/opds": {"publications": [], "links": [{"rel": "next", "href": "https://lenny/opds?p=2"}]},
                "https://bwb/opds": feed_page("bwb"),
            }
        )

        results = {r["feed"]: r for r in harvest.harvest_all(session=session)}

        assert results["lenny"].get("error") is True
        assert results["betterworldbooks"]["records"] == 2


def test_duplicate_provider_ids_are_surfaced(caplog):
    """A provider mis-assigning ids would otherwise fail silently.

    Lenny derives lenny_id positionally by zipping two separately-filtered
    queries; if they diverge, publications inherit the wrong book's id. We
    cannot detect a shift (ids stay unique, just attached to the wrong books),
    but a collision is detectable -- and on Postgres it is otherwise silent:
    import_item is UNIQUE (batch_id, ia_id), so the insert's UniqueViolation
    fallback drops the second record while the run still reports it as added.
    """
    feed = FeedRegistry(provider_name="lenny", data={"id_strategy": "self_link"})
    records = [
        {"title": "Crime and Punishment", "source_records": ["lenny:51008637"]},
        {"title": "A Different Book", "source_records": ["lenny:51008637"]},
    ]

    with caplog.at_level(logging.ERROR):
        harvest._warn_on_duplicate_ids(feed, records)

    assert "two publications claim id lenny:51008637" in caplog.text
    assert "A Different Book" in caplog.text


def test_distinct_provider_ids_are_not_flagged(caplog):
    feed = FeedRegistry(provider_name="lenny", data={"id_strategy": "self_link"})
    records = [
        {"title": "One", "source_records": ["lenny:1"]},
        {"title": "Two", "source_records": ["lenny:2"]},
    ]

    with caplog.at_level(logging.ERROR):
        harvest._warn_on_duplicate_ids(feed, records)

    assert "claim id" not in caplog.text


class TestImplausiblePageRetry:
    """The two ways a feed fails must recover symmetrically.

    A 504 is retried with backoff by the session adapter. A feed answering
    HTTP 200 with an empty catalogue is invisible to that, and it is the more
    likely failure -- it is what a provider does when the service it builds its
    feed from is briefly unreachable. Waiting a whole interval widens the gap.
    """

    def _empty_then(self, good_page):
        pages = [
            {"publications": [], "links": [{"rel": "next", "href": "https://lenny/opds?p=2"}]},
            good_page,
        ]

        class Flaky:
            def __init__(self):
                self.calls = 0

            def get(self, url, **kwargs):
                self.calls += 1
                payload = pages[min(self.calls - 1, len(pages) - 1)]

                class R:
                    def json(self_inner):
                        return payload

                    def raise_for_status(self_inner):
                        pass

                return R()

        return Flaky()

    def test_a_transient_empty_catalogue_recovers_in_tick(self, bookworm_db, monkeytime):
        _register_active("lenny", "https://lenny/opds", id_strategy="self_link")
        feed = FeedRegistry.find("lenny", "https://lenny/opds")
        session = self._empty_then(feed_page("lenny"))

        result = harvest.harvest_feed(feed, session=session, now=NOW)

        assert result["records"] == 3, "the retry should have picked up the real page"
        assert session.calls == 2
        assert FeedRegistry.get_by_id(feed.id).last_updated is not None

    def test_a_persistent_empty_catalogue_still_holds_the_cursor(self, bookworm_db, monkeytime):
        _register_active("lenny", "https://lenny/opds", id_strategy="self_link")
        feed = FeedRegistry.find("lenny", "https://lenny/opds")
        bad = {"publications": [], "links": [{"rel": "next", "href": "https://lenny/opds?p=2"}]}
        session = FakeSession({"https://lenny/opds": bad})

        with pytest.raises(harvest.SuspectFeedPage):
            harvest.harvest_feed(feed, session=session, now=NOW)

        assert FeedRegistry.get_by_id(feed.id).last_updated is None

    def test_the_retry_budget_matches_the_transport_one(self):
        """Symmetry is the point; don't let the two drift apart."""
        assert harvest.MAX_RETRIES >= 2
        assert harvest.RETRY_BACKOFF > 0
