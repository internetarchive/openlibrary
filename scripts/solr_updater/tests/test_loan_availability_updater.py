"""Tests for loan_availability_updater.py"""

import datetime
import logging
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from openlibrary.core import lending
from openlibrary.core.lending import CheckedOutSeedIncomplete
from openlibrary.utils.solr import Solr
from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI
from scripts.solr_updater.loan_availability_updater import (
    EBOOK_AVAILABLE,
    EBOOK_UNAVAILABLE,
    SOLR_QUERY_CHUNK,
    SOLR_UNAVAILABLE_MAX,
    PollRefused,
    SolrWriteFailed,
    build_poll_updates,
    fetch_solr_unavailable,
    main,
    older_than_es,
    resolve_edition_keys,
    solr_update_in_place,
)

BORROW_ROW = {
    "identifier": "bookabc",
    "uid": 100,
    "event_type": "borrow",
    "extra": '{"until": "2026-05-15 10:00:00"}',
}
RETURN_ROW = {
    "identifier": "bookabc",
    "uid": 200,
    "event_type": "return",
    "extra": "{}",
}
BROWSE_ROW = {
    "identifier": "bookxyz",
    "uid": 150,
    "event_type": "browse",
    "extra": '{"until": "2026-05-02 12:00:00"}',
}
EXPIRE_ROW = {
    "identifier": "bookxyz",
    "uid": 300,
    "event_type": "expire_browse",
    "extra": "{}",
}
ID_TO_EDITION = {
    "bookabc": {"key": "/books/OL1M", "root": "/works/OL1W"},
    "bookxyz": {"key": "/books/OL2M", "root": "/works/OL2W"},
}

AVAILABLE = {"status": "borrow_available", "available_to_browse": True, "available_to_borrow": True}
UNAVAILABLE = {"status": "borrow_unavailable", "available_to_browse": False, "available_to_borrow": False}


# ---------------------------------------------------------------------------
# collect_dirty_identifiers — the feed only nominates ids, it decides nothing
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# build_solr_updates — ground truth decides, not the event
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Cold start: the one place that DOES depend on ground truth
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Solr plumbing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_edition_keys_empty():
    assert await resolve_edition_keys([]) == {}


@pytest.mark.asyncio
async def test_resolve_edition_keys_basic():
    mock_result = MagicMock()
    mock_result.docs = [
        {"key": "/books/OL1M", "ia": ["bookabc", "bookdef"], "_root_": "/works/OL1W"},
        {"key": "/books/OL2M", "ia": ["bookxyz"], "_root_": "/works/OL2W"},
    ]
    with patch("scripts.solr_updater.loan_availability_updater.get_solr", return_value=MagicMock(spec=Solr)) as mock_get_solr:
        mock_get_solr.return_value.select_async.return_value = mock_result
        result = await resolve_edition_keys(["bookabc", "bookxyz"])

    assert result == {
        "bookabc": {"key": "/books/OL1M", "root": "/works/OL1W", "ocaid": "bookabc"},
        "bookxyz": {"key": "/books/OL2M", "root": "/works/OL2W", "ocaid": "bookxyz"},
    }
    call_args = str(mock_get_solr.return_value.select_async.call_args)
    # Must scope to edition docs -- a flat ia:(...) query would also match the
    # parent work's aggregate ia field.
    assert "type:edition" in call_args
    # Identifiers must be quoted in the Solr query
    assert '"bookabc"' in call_args
    assert '"bookxyz"' in call_args


@pytest.mark.asyncio
async def test_resolve_edition_keys_escapes_quotes():
    """An ocaid with a quote/backslash must be escaped, not form a malformed Lucene
    query (which would stall the poller forever)."""
    mock_result = MagicMock()
    mock_result.docs = []
    with patch("scripts.solr_updater.loan_availability_updater.get_solr", return_value=MagicMock(spec=Solr)) as mock_get_solr:
        mock_get_solr.return_value.select_async.return_value = mock_result
        await resolve_edition_keys(['ev"il', "back\\slash"])
    query = mock_get_solr.return_value.select_async.call_args.kwargs["query"]
    assert '\\"' in query  # embedded quote backslash-escaped
    assert "\\\\" in query  # embedded backslash escaped


@pytest.mark.asyncio
async def test_solr_update_in_place_raises_on_nonzero_status():
    """Solr can 400 on a rejected in-place update while update_in_place_async returns
    the parsed body without raising. This must surface as an exception here rather
    than being silently accepted."""
    with patch("scripts.solr_updater.loan_availability_updater.get_solr", return_value=MagicMock(spec=Solr)) as mock_get_solr:
        mock_get_solr.return_value.update_in_place_async.return_value = {
            "responseHeader": {"status": 400},
            "error": {"msg": "Can not satisfy 'update.partial.requireInPlace'"},
        }
        with pytest.raises(RuntimeError, match="Solr rejected the in-place update"):
            await solr_update_in_place([{"key": "/books/OL1M"}])


@pytest.mark.asyncio
async def test_a_large_write_is_split_into_batches():
    """One request for the whole cycle reliably timed out even at 60s. A cold
    start marks the entire unavailable set, and an atomic in-place update
    costs real work per document, so the fix is fewer documents per request."""
    request = [{"key": f"/books/OL{i}M", "_root_": "/works/OL1W", "ebook_unavailable": {"set": EBOOK_UNAVAILABLE}} for i in range(250)]
    solr = MagicMock(spec=Solr)
    solr.update_in_place_async = AsyncMock(return_value={"responseHeader": {"status": 0}})
    with patch("scripts.solr_updater.loan_availability_updater.get_solr", return_value=solr):
        await solr_update_in_place(request)
    sizes = [len(call.args[0]) for call in solr.update_in_place_async.call_args_list]
    assert sizes == [100, 100, 50], f"250 updates should go as three batches, got {sizes}"
    assert sum(sizes) == 250, "and every update must be written exactly once"


@pytest.mark.asyncio
async def test_marks_are_written_before_clears_so_a_partial_run_is_safe():
    """Once a write can partially land, order IS the safety property: stopping
    after the marks hides books, which the next poll fixes. Stopping after the
    clears publishes checked-out books as borrowable."""
    marks = [{"key": f"/books/OL{i}M", "_root_": "/works/OL1W", "ebook_unavailable": {"set": EBOOK_UNAVAILABLE}} for i in range(120)]
    clears = [{"key": f"/books/OL{i}M", "_root_": "/works/OL1W", "ebook_unavailable": {"set": EBOOK_AVAILABLE}} for i in range(120, 140)]
    solr = MagicMock(spec=Solr)
    solr.update_in_place_async = AsyncMock(return_value={"responseHeader": {"status": 0}})
    with patch("scripts.solr_updater.loan_availability_updater.get_solr", return_value=solr):
        await solr_update_in_place(marks + clears)
    written = [doc for call in solr.update_in_place_async.call_args_list for doc in call.args[0]]
    assert len(written) == 140, "every update written exactly once"
    positions = [i for i, d in enumerate(written) if d["ebook_unavailable"] == {"set": EBOOK_AVAILABLE}]
    # EVERY mark before EVERY clear. Asserting only that nothing precedes the
    # FIRST clear is satisfied by any order whose first document is a mark --
    # a reversed batch sequence passed it.
    assert positions == list(range(140 - 20, 140)), f"all 20 clears must come last, found them at {positions[:5]}..."


@pytest.mark.asyncio
async def test_a_failure_says_how_many_batches_had_already_landed(caplog):
    """ "Nothing was written" and "most of it was written" need different
    responses from whoever reads the log, so the message distinguishes them."""
    request = [{"key": f"/books/OL{i}M", "_root_": "/works/OL1W", "ebook_unavailable": {"set": EBOOK_UNAVAILABLE}} for i in range(250)]
    solr = MagicMock(spec=Solr)
    solr.update_in_place_async = AsyncMock(side_effect=[{"responseHeader": {"status": 0}}, {"responseHeader": {"status": 400}}])
    with (
        patch("scripts.solr_updater.loan_availability_updater.get_solr", return_value=solr),
        pytest.raises(SolrWriteFailed, match="batch 2 of 3 failed after 1 had already been written"),
    ):
        await solr_update_in_place(request)


@pytest.mark.asyncio
async def test_a_refused_write_is_logged_with_the_batch_it_refused(caplog):
    """Solr answers 400 for the whole request and names no document, so the
    batch's shape and a sample key are what make it diagnosable."""
    batch = [{"key": "/books/OL1M", "_root_": "/works/OL1W", "ebook_unavailable": {"set": EBOOK_UNAVAILABLE}}]
    solr = MagicMock(spec=Solr)
    solr.update_in_place_async = AsyncMock(return_value={"responseHeader": {"status": 400}, "error": {"msg": "no in-place update"}})
    with (
        patch("scripts.solr_updater.loan_availability_updater.get_solr", return_value=solr),
        caplog.at_level(logging.ERROR, logger="openlibrary.loan-availability-updater"),
        pytest.raises(SolrWriteFailed),
    ):
        await solr_update_in_place(batch)
    assert "/books/OL1M" in caplog.text
    assert "no in-place update" in caplog.text, "Solr's own words, not just our summary"


@pytest.mark.asyncio
async def test_solr_update_in_place_propagates_transport_errors():
    with patch("scripts.solr_updater.loan_availability_updater.get_solr", return_value=MagicMock(spec=Solr)) as mock_get_solr:
        mock_get_solr.return_value.update_in_place_async.side_effect = RuntimeError("Solr unreachable")
        with pytest.raises(RuntimeError, match="Solr unreachable"):
            await solr_update_in_place([{"key": "/books/OL1M"}])


# ---------------------------------------------------------------------------
# build_recheck_updates — the drift safety net
# ---------------------------------------------------------------------------


def _recheck_docs():
    mock_result = MagicMock()
    mock_result.docs = [
        {"key": "/books/OL99M", "ia": ["freed"], "_root_": "/works/OL99W"},
        {"key": "/books/OL100M", "ia": ["stillout"], "_root_": "/works/OL100W"},
    ]
    return mock_result


# ---------------------------------------------------------------------------
# main() — daemon error-handling integration tests
#
# Strategy: pre-seed the state file so read_state() returns 99 (skipping the
# startup init path), then control lending.get_loan_changes to return one
# batch then raise SystemExit to terminate the infinite loop.  The state file
# content after the test reveals whether write_state was called.
# ---------------------------------------------------------------------------

_RETURN_ROW = {
    "identifier": "bookabc",
    "uid": 100,
    "event_type": "return",
    "extra": "{}",
}
# Acquiring, so the steady-state path actually writes. A releasing row writes
# nothing by design, which makes it useless for exercising the write sites.
_BORROW_ROW = {
    "identifier": "bookabc",
    "uid": 100,
    "event_type": "borrow",
    "extra": '{"until": "2026-05-15 10:00:00"}',
}
_RESOLVE_RESULT = MagicMock()
_RESOLVE_RESULT.docs = [{"key": "/books/OL1M", "ia": ["bookabc"], "_root_": "/works/OL1W"}]
_EMPTY_RESULT = MagicMock()
_EMPTY_RESULT.docs = []
_RECHECK_RESULT = MagicMock()
_RECHECK_RESULT.docs = [{"key": "/books/OL99M", "ia": ["stale"], "_root_": "/works/OL99W"}]

_OK_RESPONSE = {"responseHeader": {"status": 0}}


def _select_side_effect(*args, **kwargs):
    """Route Solr select calls to the right fixture by query content."""
    query = kwargs.get("query", "") or (args[0] if args else "")
    if "ia:" in query:
        return _RESOLVE_RESULT
    # ebook_unavailable:1 → re-check candidates (empty unless overridden)
    return _EMPTY_RESULT


# ---------------------------------------------------------------------------
# Cold start inside main()
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Findings from the adversarial review of the first revision
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_edition_keys_chunks_its_query():
    """The cold start hands over every identifier touched in 14 days. One
    clause per identifier against Solr's maxBooleanClauses (30000 in
    production) failed the whole query, which propagated out of the cold start
    and killed the process before any state was written -- so the daemon could
    never complete a cold start at all, on every restart."""
    identifiers = [f"ocaid_{i}" for i in range(SOLR_QUERY_CHUNK * 3 + 7)]
    mock_solr = MagicMock(spec=Solr)
    mock_solr.select_async.return_value = MagicMock(docs=[])
    with patch("scripts.solr_updater.loan_availability_updater.get_solr", return_value=mock_solr):
        await resolve_edition_keys(identifiers)

    assert mock_solr.select_async.call_count == 4
    for call in mock_solr.select_async.call_args_list:
        terms = call.kwargs["query"].count('"') // 2
        assert terms <= SOLR_QUERY_CHUNK, f"a chunk carried {terms} clauses"


@pytest.mark.asyncio
async def test_resolve_edition_keys_still_resolves_across_chunks():
    """Chunking must not lose results at the seams."""
    identifiers = [f"ocaid_{i}" for i in range(SOLR_QUERY_CHUNK + 2)]
    first, last = identifiers[0], identifiers[-1]

    def select(query, **kwargs):
        docs = []
        if f'"{first}"' in query:
            docs.append({"key": "/books/OL1M", "ia": [first], "_root_": "/works/OL1W"})
        if f'"{last}"' in query:
            docs.append({"key": "/books/OL2M", "ia": [last], "_root_": "/works/OL2W"})
        return MagicMock(docs=docs)

    mock_solr = MagicMock(spec=Solr)
    mock_solr.select_async.side_effect = select
    with patch("scripts.solr_updater.loan_availability_updater.get_solr", return_value=mock_solr):
        resolved = await resolve_edition_keys(identifiers)
    assert set(resolved) == {first, last}


# ---------------------------------------------------------------------------
# Waitlists: the case that decides whether the whole asymmetry holds
# ---------------------------------------------------------------------------

WAITLISTED = {
    "status": "borrow_unavailable",
    "available_to_browse": False,
    "available_to_borrow": False,
    "available_to_waitlist": True,
    "num_waitlist": "3",
}


# ---------------------------------------------------------------------------
# Index seed + overlap replay
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Poll-and-reconcile (v3). One read of the index's unavailable set, one read of
# what Solr has marked, one bulk update carrying both directions.
#
# `resolve_edition_keys` and `fetch_solr_unavailable` are patched out: they have
# their own tests, and what these pin is the set arithmetic and the guard --
# which is where a defect publishes a checked-out book as borrowable.
# ---------------------------------------------------------------------------

POLL_EDITIONS = {
    "bookaaa": {"key": "/books/OL1M", "root": "/works/OL1W", "ocaid": "bookaaa"},
    "bookbbb": {"key": "/books/OL2M", "root": "/works/OL2W", "ocaid": "bookbbb"},
    "bookccc": {"key": "/books/OL3M", "root": "/works/OL3W", "ocaid": "bookccc"},
}

# A loan-event time the index could plausibly return, fixed so assertions can
# name it. 2026-10-07T20:00:00Z, verified against the parser rather than
# arithmetic -- the first value written here was a day out.
EVENT_EPOCH = 1791403200


def _index(*identifiers: str, at: int | None = EVENT_EPOCH) -> dict[str, int | None]:
    """What the index now returns: identifier -> loan-event epoch, or None.

    Defaults to a real event time because a real poll almost always has one:
    68% of the live unavailable set carries `lending___last_browse`, and ONE
    dated record is enough to give the clear-gate its horizon. Defaulting to
    None would leave every test without a horizon, which blocks all clearing
    and would quietly turn the clear-path tests into no-ops.

    Pass `at=None` for the case where the index knows nothing about timing.
    """
    return dict.fromkeys(identifiers, at)


def _marked(*keys: str) -> dict[str, dict]:
    by_key = {info["key"]: (ia, info) for ia, info in POLL_EDITIONS.items()}
    return {key: {"key": key, "ia": [by_key[key][0]], "_root_": by_key[key][1]["root"]} for key in keys}


def _poll(identifiers: list[str], marked: dict[str, dict]):
    resolved = {ia: POLL_EDITIONS[ia] for ia in identifiers if ia in POLL_EDITIONS}
    return (
        patch("scripts.solr_updater.loan_availability_updater.resolve_edition_keys", AsyncMock(return_value=resolved)),
        patch("scripts.solr_updater.loan_availability_updater.fetch_solr_unavailable", AsyncMock(return_value=marked)),
    )


def _sets(updates: list[dict]) -> tuple[set[str], set[str]]:
    """(keys set to unavailable, keys set to available)."""
    mark = {u["key"] for u in updates if u["ebook_unavailable"] == {"set": EBOOK_UNAVAILABLE}}
    clear = {u["key"] for u in updates if u["ebook_unavailable"] == {"set": EBOOK_AVAILABLE}}
    return mark, clear


@pytest.mark.asyncio
async def test_a_poll_marks_a_newly_unavailable_book():
    resolve, marked = _poll(["bookaaa", "bookbbb"], _marked("/books/OL1M"))
    with resolve, marked:
        updates = await build_poll_updates(_index("bookaaa", "bookbbb"))
    mark, clear = _sets(updates)
    assert mark == {"/books/OL2M"}, "the book the index newly calls unavailable must be marked"
    assert clear == set(), "nothing freed up, so nothing may be cleared"
    assert all("_root_" in u for u in updates), "an in-place update on a nested child needs its parent key"


@pytest.mark.asyncio
async def test_a_poll_clears_a_book_the_index_no_longer_calls_unavailable():
    """The case the repairer used to own. The index reflects expiry directly,
    so a book dropping out of the set is a return or an expiry."""
    resolve, marked = _poll(["bookaaa"], _marked("/books/OL1M", "/books/OL2M"))
    with resolve, marked:
        updates = await build_poll_updates(_index("bookaaa"))
    mark, clear = _sets(updates)
    assert clear == {"/books/OL2M"}
    assert mark == set()


@pytest.mark.asyncio
async def test_a_wiped_field_is_re_marked_by_the_next_poll():
    """HEADLINE. A reindex rewrites edition documents and drops
    `ebook_unavailable` entirely, which under the previous design stranded
    every checked-out book as borrowable until someone re-ran a cold start by
    hand. Here the next poll sees an empty marked set, and the whole
    unavailable set is simply marked again. No operator step exists to forget.
    """
    resolve, marked = _poll(list(POLL_EDITIONS), {})
    with resolve, marked:
        updates = await build_poll_updates(_index(*POLL_EDITIONS))
    mark, clear = _sets(updates)
    assert mark == {"/books/OL1M", "/books/OL2M", "/books/OL3M"}
    assert clear == set(), "an empty marked set has nothing to clear -- and must not invent any"


@pytest.mark.asyncio
async def test_an_unchanged_poll_writes_nothing():
    """Idempotence is what makes a 30-second cadence affordable: a steady state
    costs one read and zero writes, so write volume tracks real lending churn
    rather than the poll rate."""
    resolve, marked = _poll(["bookaaa", "bookbbb"], _marked("/books/OL1M", "/books/OL2M"))
    with resolve, marked:
        updates = await build_poll_updates(_index("bookaaa", "bookbbb"))
    assert updates == []


def _many_marked(n: int) -> dict[str, dict]:
    return {f"/books/OL{i}M": {"key": f"/books/OL{i}M", "ia": [f"book{i}"], "_root_": f"/works/OL{i}W"} for i in range(n)}


@pytest.mark.asyncio
async def test_a_truncated_marked_read_is_refused_rather_than_treated_as_the_set():
    """An edition outside a capped read is indistinguishable from one the index
    no longer calls unavailable, and the reconcile clears on absence."""
    mock_solr = MagicMock(spec=Solr)
    mock_solr.select_async.return_value = MagicMock(docs=[{"key": f"/books/OL{i}M", "ia": [], "_root_": "/works/OL1W"} for i in range(SOLR_UNAVAILABLE_MAX)])
    with patch("scripts.solr_updater.loan_availability_updater.get_solr", return_value=mock_solr), pytest.raises(PollRefused) as excinfo:
        await fetch_solr_unavailable()
    assert "cap" in str(excinfo.value)


# ---------------------------------------------------------------------------
# The clear gate: absence means "returned" only for marks OLDER than the index.
# ---------------------------------------------------------------------------


def _marked_at(key: str, ocaid: str, stamp: int | None) -> dict:
    doc: dict = {"key": key, "ia": [ocaid], "_root_": key.replace("books", "works").replace("M", "W")}
    if stamp is not None:
        doc["ebook_unavailable_ts"] = stamp
    return doc


@pytest.mark.asyncio
async def test_a_mark_newer_than_the_index_is_held_not_cleared():
    """THE SEAM. The index's snapshot is current only up to its newest_es_event loan
    event. A mark newer than that is absent from the result set because the
    index has not caught up -- not because the book came back. Clearing it
    publishes a checked-out book as borrowable and nothing revisits it.
    """
    marked = {"/books/OL2M": _marked_at("/books/OL2M", "bookbbb", EVENT_EPOCH + 60)}
    with (
        patch("scripts.solr_updater.loan_availability_updater.resolve_edition_keys", AsyncMock(return_value={"bookaaa": POLL_EDITIONS["bookaaa"]})),
        patch("scripts.solr_updater.loan_availability_updater.fetch_solr_unavailable", AsyncMock(return_value=marked)),
    ):
        updates = await build_poll_updates({"bookaaa": EVENT_EPOCH})
    _, clear = _sets(updates)
    assert clear == set(), "a mark newer than the index's currency is lag, and must be held"


@pytest.mark.asyncio
async def test_a_mark_older_than_the_index_is_cleared():
    """The other half, and it matters as much: a gate that holds everything
    looks identical to a gate that works, until a book is never freed."""
    marked = {"/books/OL2M": _marked_at("/books/OL2M", "bookbbb", EVENT_EPOCH - 60)}
    with (
        patch("scripts.solr_updater.loan_availability_updater.resolve_edition_keys", AsyncMock(return_value={"bookaaa": POLL_EDITIONS["bookaaa"]})),
        patch("scripts.solr_updater.loan_availability_updater.fetch_solr_unavailable", AsyncMock(return_value=marked)),
    ):
        updates = await build_poll_updates({"bookaaa": EVENT_EPOCH})
    _, clear = _sets(updates)
    assert clear == {"/books/OL2M"}, "a mark the index is current enough to contradict must clear"


def test_a_mark_exactly_at_the_index_currency_is_held():
    """Strict `<`. The index is current up to and INCLUDING that instant, so a
    mark at the same second is the ambiguous case, and ambiguity holds."""
    doc = _marked_at("/books/OL2M", "bookbbb", EVENT_EPOCH)
    clearable, held = older_than_es([doc], EVENT_EPOCH)
    assert clearable == []
    assert held == [doc]


def test_no_index_horizon_clears_nothing():
    """An empty result set, or one where nothing carries an event time, is NO
    INFORMATION -- never "everything was returned". This is what makes a
    collapsed index safe rather than catastrophic."""
    doc = _marked_at("/books/OL2M", "bookbbb", 1)
    clearable, held = older_than_es([doc], None)
    assert clearable == []
    assert held == [doc]


def test_a_mark_with_no_stamp_is_treated_as_very_old_and_clears():
    """Decided, not inherited. Only reachable for a mark written between the
    schema deploy and this code shipping: a reindex that wipes the stamp wipes
    `ebook_unavailable` with it, so such a document leaves the marked set
    rather than lingering stampless. Those marks really are old, and holding
    them forever is the worse failure."""
    doc = _marked_at("/books/OL2M", "bookbbb", None)
    clearable, held = older_than_es([doc], EVENT_EPOCH)
    assert clearable == [doc]
    assert held == []


# ---------------------------------------------------------------------------
# The timestamp: WHEN THE LOAN STARTED, not when the daemon noticed.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_mark_is_stamped_with_the_loan_event_not_the_clock():
    """THE POINT OF THE FIELD. `ebook_unavailable_ts` answers "when did this
    book become unavailable", and the daemon seeing it is a different fact --
    minutes later in a steady state, arbitrarily later after a restart.

    Stamping the read time makes every mark look as fresh as the poll that
    observed it, which is exactly backwards for a gate whose job is to tell a
    recent mark from an old one.
    """
    resolve, marked = _poll(["bookaaa"], {})
    with resolve, marked:
        updates = await build_poll_updates({"bookaaa": EVENT_EPOCH})
    assert len(updates) == 1
    assert updates[0]["ebook_unavailable_ts"]["set"] == EVENT_EPOCH, "the stamp must be the loan event time"
    assert abs(updates[0]["ebook_unavailable_ts"]["set"] - int(time.time())) > 60, "and must NOT be the daemon's clock"


@pytest.mark.parametrize(
    ("borrow", "browse", "expected"),
    [
        (EVENT_EPOCH, None, EVENT_EPOCH),
        (None, EVENT_EPOCH, EVENT_EPOCH),
        (EVENT_EPOCH, EVENT_EPOCH - 3600, EVENT_EPOCH),
        (EVENT_EPOCH - 3600, EVENT_EPOCH, EVENT_EPOCH),
    ],
    ids=["borrow-only", "browse-only", "borrow-is-later", "browse-is-later"],
)
def test_the_index_event_time_is_the_LATER_of_borrow_and_browse(borrow, browse, expected):
    """A book can have been both browsed and borrowed. The current spell of
    unavailability dates from whichever happened LAST, so min() or first-wins
    would date a fresh borrow to an old browse and make it clearable early."""
    doc = {"identifier": "bookaaa"}
    if borrow is not None:
        doc["lending___last_borrow"] = datetime.datetime.fromtimestamp(borrow, datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    if browse is not None:
        doc["lending___last_browse"] = datetime.datetime.fromtimestamp(browse, datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert lending._index_event_epoch(doc) == expected


def test_a_multi_valued_event_field_does_not_crash_the_parse():
    """Search-index fields are routinely multi-valued -- `lending___status`
    comes back as a list -- so a bare fromisoformat(doc[field]) raises on
    ordinary data. The latest value across the list is the answer."""
    doc = {
        "identifier": "bookaaa",
        "lending___last_browse": ["2026-10-07T19:00:00Z", "2026-10-07T20:00:00Z"],
    }
    assert lending._index_event_epoch(doc) == EVENT_EPOCH


def test_an_unparsable_event_time_is_skipped_rather_than_raised_on():
    """A malformed date from the index must not take the daemon down; the
    caller already has a defined answer for "no timestamp"."""
    assert lending._index_event_epoch({"identifier": "b", "lending___last_browse": "not-a-date"}) is None
    assert lending._index_event_epoch({"identifier": "b", "lending___last_browse": ["nope", "2026-10-07T20:00:00Z"]}) == EVENT_EPOCH


@pytest.mark.asyncio
async def test_a_book_with_no_event_time_is_stamped_with_the_newest_in_the_batch():
    """About a THIRD of the live unavailable set carries neither field
    (measured 2026-10-07: 268 of 857). Those need an answer, and it is the
    newest_es_event loan event anywhere in this result set -- in range by construction,
    and the conservative end of that range.

    Conservative matters: the stamp exists so a lagged poll can refuse to clear
    a mark it is too stale to contradict. Over-estimating hides a book briefly
    and corrects itself; under-estimating publishes a checked-out book and
    nothing revisits it.
    """
    resolve, marked = _poll(["bookaaa", "bookbbb"], {})
    with resolve, marked:
        # bookbbb has no event time; bookaaa is the newest_es_event thing in the batch.
        updates = await build_poll_updates({"bookaaa": EVENT_EPOCH, "bookbbb": None})
    stamps = {u["key"]: u["ebook_unavailable_ts"]["set"] for u in updates}
    assert stamps["/books/OL1M"] == EVENT_EPOCH, "the dated book keeps its own event time"
    assert stamps["/books/OL2M"] == EVENT_EPOCH, "and the undated one takes the newest_es_event in the batch"


@pytest.mark.asyncio
async def test_the_fallback_is_the_NEWEST_in_the_batch_not_the_oldest():
    """The choice of end is the whole safety property, so it is pinned
    separately from the fallback existing at all. The earliest value would also
    be "in range" and would make every undated book immediately clearable."""
    resolve, marked = _poll(["bookaaa", "bookbbb", "bookccc"], {})
    oldest, newest_es_event = EVENT_EPOCH - 86_400, EVENT_EPOCH
    with resolve, marked:
        updates = await build_poll_updates({"bookaaa": oldest, "bookbbb": newest_es_event, "bookccc": None})
    undated = next(u for u in updates if u["key"] == "/books/OL3M")
    assert undated["ebook_unavailable_ts"]["set"] == newest_es_event, "the undated book must take the NEWEST event in the batch"
    assert undated["ebook_unavailable_ts"]["set"] != oldest, "the oldest would be in range too, and would clear it immediately"


@pytest.mark.asyncio
async def test_a_batch_with_no_event_times_at_all_falls_back_to_the_clock_and_says_so(caplog):
    """The degenerate case: the index gives no event time for anything. There
    is nothing better than the daemon clock then -- but it must be LOUD, since
    it means every mark this cycle is dated to when the daemon looked rather
    than when the loans began."""
    resolve, marked = _poll(["bookaaa"], {})
    with resolve, marked, caplog.at_level(logging.WARNING, logger="openlibrary.loan-availability-updater"):
        updates = await build_poll_updates({"bookaaa": None})
    assert abs(updates[0]["ebook_unavailable_ts"]["set"] - int(time.time())) <= 5, "nothing better than the clock is available"
    assert "no loan-event time" in caplog.text
    assert "daemon clock" in caplog.text


# ---------------------------------------------------------------------------
# main() as the poll loop. One iteration, then SystemExit out of the sleep.
# ---------------------------------------------------------------------------


async def _run_poll_once(solr_mock, lending_mock, unavailable: list[str] | dict[str, int | None], dry_run: bool = False) -> None:
    # Accepts the list form for brevity at call sites that do not care about
    # loan-event times; the seed itself returns the mapping.
    seed = unavailable if isinstance(unavailable, dict) else _index(*unavailable)
    lending_mock.get_checked_out_candidates_async = AsyncMock(return_value=seed)
    lending_mock.CheckedOutSeedIncomplete = CheckedOutSeedIncomplete
    with (
        patch("scripts.solr_updater.loan_availability_updater.asyncio.sleep", AsyncMock(side_effect=SystemExit)),
        pytest.raises(SystemExit),
    ):
        await main("fake_config.yml", poll_interval=0, dry_run=dry_run)


@pytest.mark.asyncio
@patch("scripts.solr_updater.loan_availability_updater.get_solr")
@patch("scripts.solr_updater.loan_availability_updater.init_sentry")
@patch("scripts.solr_updater.loan_availability_updater.lending")
@patch("scripts.solr_updater.loan_availability_updater.infogami")
@patch("scripts.solr_updater.loan_availability_updater.load_config")
async def test_main_writes_through_update_in_place_not_bare_update(mock_config, mock_infogami, mock_lending, mock_sentry, mock_get_solr):
    """ebook_unavailable is numeric, docValues-only and unstored specifically so
    an in-place update is possible. A bare update() rewrites the document from
    what Solr has stored -- which, for an unstored field, is nothing."""
    solr = MagicMock(spec=Solr)
    mock_get_solr.return_value = solr
    solr.select_async.side_effect = _select_side_effect
    solr.update_in_place_async.return_value = _OK_RESPONSE

    with patch(
        "scripts.solr_updater.loan_availability_updater.resolve_edition_keys",
        AsyncMock(return_value={"bookabc": {"key": "/books/OL1M", "root": "/works/OL1W", "ocaid": "bookabc"}}),
    ):
        await _run_poll_once(solr, mock_lending, ["bookabc"])

    assert solr.update_in_place_async.called, "update_in_place_async() was never called"
    # `spec=Solr` means a bare update() call would raise rather than record, so
    # the assertion above is the whole check: reaching it means no other write
    # method was used.


@pytest.mark.asyncio
@patch("scripts.solr_updater.loan_availability_updater.get_solr")
@patch("scripts.solr_updater.loan_availability_updater.init_sentry")
@patch("scripts.solr_updater.loan_availability_updater.lending")
@patch("scripts.solr_updater.loan_availability_updater.infogami")
@patch("scripts.solr_updater.loan_availability_updater.load_config")
async def test_main_never_hard_commits(mock_config, mock_infogami, mock_lending, mock_sentry, mock_get_solr):
    """A hard commit opens a new searcher and invalidates every Solr cache on
    the instance serving openlibrary.org. At POLL_INTERVAL that would be ~5,760
    a day, and it buys nothing: autoSoftCommit makes the write visible within a
    second and autoCommit persists it."""
    solr = MagicMock(spec=Solr)
    mock_get_solr.return_value = solr
    solr.select_async.side_effect = _select_side_effect
    solr.update_in_place_async.return_value = _OK_RESPONSE

    with patch(
        "scripts.solr_updater.loan_availability_updater.resolve_edition_keys",
        AsyncMock(return_value={"bookabc": {"key": "/books/OL1M", "root": "/works/OL1W", "ocaid": "bookabc"}}),
    ):
        await _run_poll_once(solr, mock_lending, ["bookabc"])

    commits = [c for c in solr.update_in_place_async.call_args_list if c.kwargs.get("commit")]
    assert commits == [], f"expected no hard commit, got {len(commits)}"


@pytest.mark.asyncio
@patch("scripts.solr_updater.loan_availability_updater.get_solr")
@patch("scripts.solr_updater.loan_availability_updater.init_sentry")
@patch("scripts.solr_updater.loan_availability_updater.lending")
@patch("scripts.solr_updater.loan_availability_updater.infogami")
@patch("scripts.solr_updater.loan_availability_updater.load_config")
async def test_main_keeps_prior_state_when_the_index_read_is_refused(mock_config, mock_infogami, mock_lending, mock_sentry, mock_get_solr):
    """An incomplete index read must not reach Solr at all. The previous poll's
    marks are a better answer than a partial one, and at this cadence raising
    would be a crash loop rather than a signal."""
    solr = MagicMock(spec=Solr)
    mock_get_solr.return_value = solr
    solr.select_async.side_effect = _select_side_effect
    mock_lending.get_checked_out_candidates_async = AsyncMock(side_effect=CheckedOutSeedIncomplete("short read"))
    mock_lending.CheckedOutSeedIncomplete = CheckedOutSeedIncomplete

    with (
        patch("scripts.solr_updater.loan_availability_updater.asyncio.sleep", AsyncMock(side_effect=SystemExit)),
        pytest.raises(SystemExit),
    ):
        await main("fake_config.yml", poll_interval=0)

    assert not solr.update_in_place_async.called, "a refused poll must write nothing"


@pytest.mark.asyncio
@patch("scripts.solr_updater.loan_availability_updater.get_solr")
@patch("scripts.solr_updater.loan_availability_updater.init_sentry")
@patch("scripts.solr_updater.loan_availability_updater.lending")
@patch("scripts.solr_updater.loan_availability_updater.infogami")
@patch("scripts.solr_updater.loan_availability_updater.load_config")
async def test_main_writes_nothing_on_a_dry_run(mock_config, mock_infogami, mock_lending, mock_sentry, mock_get_solr):
    solr = MagicMock(spec=Solr)
    mock_get_solr.return_value = solr
    solr.select_async.side_effect = _select_side_effect

    with patch(
        "scripts.solr_updater.loan_availability_updater.resolve_edition_keys",
        AsyncMock(return_value={"bookabc": {"key": "/books/OL1M", "root": "/works/OL1W", "ocaid": "bookabc"}}),
    ):
        await _run_poll_once(solr, mock_lending, ["bookabc"], dry_run=True)

    assert not solr.update_in_place_async.called


# ---------------------------------------------------------------------------
# Defects found by adversarial review 2026-10-06. Each test below exists
# because the thing it pins was broken and shipped, not because it seemed
# worth asserting.
# ---------------------------------------------------------------------------


def test_the_shipped_launcher_invocation_matches_mains_signature():
    """The launcher passed --state-file long after main() stopped taking it.

    argparse exits 2 before the first poll, the supervisor sleeps 60s and tries
    again, and the container stays healthy while the feature is completely
    inert -- the only symptom is a usage string in the log once a minute. No
    test caught it because every other test calls main() as a Python function
    and never goes through the CLI the deployment actually uses.
    """
    script = (Path(__file__).parents[2] / "solr_updater" / ".." / ".." / "docker" / "ol-solr-updater-start.sh").resolve()
    text = script.read_text()
    assert "loan_availability_updater.py" in text, f"launcher not found at {script}"

    # The invocation, joined across backslash continuations.
    invocation = ""
    for line in text.replace("\\\n", " ").splitlines():
        if "loan_availability_updater.py" in line:
            invocation = line
            break
    flags = [token for token in invocation.split() if token.startswith("--")]

    parser = FnToCLI(main).parser
    known = {action.option_strings[0] for action in parser._actions if action.option_strings}
    unknown = [f for f in flags if f not in known]
    assert not unknown, f"launcher passes {unknown} which main() does not accept; known flags are {sorted(known)}"


@pytest.mark.asyncio
async def test_a_truncated_marked_read_is_refused_rather_than_cleared():
    """Solr returns HTTP 200 with a short `docs` list in two ways -- more
    matched than `rows` asked for, and `timeAllowed` cutting the query short.
    The reconcile turns ABSENCE into a clear, so either one is a mass clear by
    a quiet route."""
    mock_solr = MagicMock(spec=Solr)
    result = MagicMock(docs=[{"key": "/books/OL1M", "ia": ["bookaaa"], "_root_": "/works/OL1W"}], num_found=500, response_header={})
    mock_solr.select_async.return_value = result
    with patch("scripts.solr_updater.loan_availability_updater.get_solr", return_value=mock_solr), pytest.raises(PollRefused) as excinfo:
        await fetch_solr_unavailable()
    assert "500" in str(excinfo.value)


@pytest.mark.asyncio
async def test_a_partial_solr_read_is_refused_rather_than_cleared():
    """`partialResults` is the only signal that `timeAllowed` tripped; numFound
    can look consistent with the short list it returned."""
    mock_solr = MagicMock(spec=Solr)
    result = MagicMock(docs=[{"key": "/books/OL1M", "ia": ["bookaaa"], "_root_": "/works/OL1W"}], num_found=1, response_header={"partialResults": True})
    mock_solr.select_async.return_value = result
    with patch("scripts.solr_updater.loan_availability_updater.get_solr", return_value=mock_solr), pytest.raises(PollRefused) as excinfo:
        await fetch_solr_unavailable()
    assert "partialResults" in str(excinfo.value)


@pytest.mark.asyncio
async def test_a_mark_carries_the_timestamp_in_the_same_update():
    """The mark and its stamp are ONE update, not two.

    Separate writes could interleave with a clear, leaving a mark whose stamp
    belongs to a different write -- and the gate judges marks by that stamp.
    """
    resolve, marked = _poll(["bookaaa"], {})
    with resolve, marked:
        updates = await build_poll_updates(_index("bookaaa"))
    assert len(updates) == 1
    assert updates[0]["ebook_unavailable"] == {"set": EBOOK_UNAVAILABLE}
    # Pinned to the exact event time rather than "greater than some constant".
    # A review proved the looser form green against BOTH a milliseconds bug
    # (int(time.time() * 1000)) and a frozen constant -- either of which makes
    # every mark newer than the index's currency forever, so the gate holds
    # every clear and availability freezes, with nothing going red. Equality
    # against a known epoch catches both, and now catches a third: the stamp
    # silently reverting to the daemon's clock.
    assert updates[0]["ebook_unavailable_ts"]["set"] == EVENT_EPOCH


@pytest.mark.asyncio
async def test_a_clear_does_not_touch_the_timestamp():
    """`requireInPlace` cannot set a field to null, so a clear leaves the old
    value behind -- verified against a live Solr, not assumed. The field is
    therefore meaningful only while `ebook_unavailable` is 1, and a re-mark
    overwrites it."""
    resolve, marked = _poll(["bookaaa"], _marked("/books/OL2M"))
    with resolve, marked:
        updates = await build_poll_updates(_index("bookaaa"))
    clear = [u for u in updates if u["ebook_unavailable"] == {"set": EBOOK_AVAILABLE}]
    assert len(clear) == 1
    assert "ebook_unavailable_ts" not in clear[0]


@pytest.mark.asyncio
async def test_a_truncated_edition_resolve_is_refused_rather_than_cleared():
    """The other half of the comparison that turns absence into a clear.

    `fetch_solr_unavailable` carried this guard and `resolve_edition_keys` did
    not, though an identifier that fails to resolve is indistinguishable from
    one the index no longer calls unavailable. A Solr slowdown tripping
    `timeAllowed` returns HTTP 200 with a short `docs` list and
    `partialResults`, and without this the editions that fell off the end are
    cleared -- checked-out books published as borrowable, with nothing above
    INFO in the log.
    It needs a slow Solr, not an index incident.
    """
    mock_solr = MagicMock(spec=Solr)
    mock_solr.select_async.return_value = MagicMock(
        docs=[{"key": "/books/OL1M", "ia": ["bookaaa"], "_root_": "/works/OL1W"}],
        num_found=766,
        response_header={},
    )
    with patch("scripts.solr_updater.loan_availability_updater.get_solr", return_value=mock_solr), pytest.raises(PollRefused) as excinfo:
        await resolve_edition_keys(["bookaaa", "bookbbb"])
    assert "resolve" in str(excinfo.value)


@pytest.mark.asyncio
async def test_a_partial_edition_resolve_is_refused_rather_than_cleared():
    """`partialResults` is the only signal that `timeAllowed` cut the query
    short; `numFound` can look perfectly consistent with the short list."""
    mock_solr = MagicMock(spec=Solr)
    mock_solr.select_async.return_value = MagicMock(
        docs=[{"key": "/books/OL1M", "ia": ["bookaaa"], "_root_": "/works/OL1W"}],
        num_found=1,
        response_header={"partialResults": True},
    )
    with patch("scripts.solr_updater.loan_availability_updater.get_solr", return_value=mock_solr), pytest.raises(PollRefused):
        await resolve_edition_keys(["bookaaa"])


@pytest.mark.asyncio
async def test_identifiers_with_no_edition_are_not_mistaken_for_a_truncated_read():
    """THE DISTINCTION THE GUARD HAS TO MAKE. Most IA identifiers have no OL
    edition, so a chunk of 500 resolving to 3 documents is the normal case, not
    a short read -- and a guard that refused it would halt the daemon
    permanently on ordinary data.

    `num_found` counts MATCHING documents, so 3 matched and 3 returned is
    complete. The guard fires on Solr matching more than it handed back, which
    is a different thing entirely.
    """
    mock_solr = MagicMock(spec=Solr)
    mock_solr.select_async.return_value = MagicMock(
        docs=[{"key": "/books/OL1M", "ia": ["bookaaa"], "_root_": "/works/OL1W"}],
        num_found=1,
        response_header={},
    )
    with patch("scripts.solr_updater.loan_availability_updater.get_solr", return_value=mock_solr):
        resolved = await resolve_edition_keys(["bookaaa", "bookbbb", "bookccc"])
    assert resolved == {"bookaaa": {"key": "/books/OL1M", "root": "/works/OL1W", "ocaid": "bookaaa"}}


@pytest.mark.asyncio
async def test_more_editions_than_identifiers_is_not_mistaken_for_a_truncated_read():
    """The other direction of the same distinction, and the one that would halt
    the daemon rather than silently clear.

    Two editions can share an ocaid, so a chunk of 2 identifiers legitimately
    matches 3 documents. A guard comparing `num_found` against the number of
    IDENTIFIERS requested — rather than against the documents returned — reads
    that as a short read and raises, every poll, forever. The comparison has to
    be returned-versus-matched, not requested-versus-matched.
    """
    docs = [
        {"key": "/books/OL1M", "ia": ["bookaaa"], "_root_": "/works/OL1W"},
        {"key": "/books/OL2M", "ia": ["bookaaa"], "_root_": "/works/OL2W"},
        {"key": "/books/OL3M", "ia": ["bookbbb"], "_root_": "/works/OL3W"},
    ]
    mock_solr = MagicMock(spec=Solr)
    mock_solr.select_async.return_value = MagicMock(docs=docs, num_found=3, response_header={})
    with patch("scripts.solr_updater.loan_availability_updater.get_solr", return_value=mock_solr):
        resolved = await resolve_edition_keys(["bookaaa", "bookbbb"])
    assert set(resolved) == {"bookaaa", "bookbbb"}
