"""Tests for loan_availability_updater.py"""

import contextlib
import datetime
import logging
import os
import subprocess
import sys
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
    MARKED_SET_MAX,
    SOLR_QUERY_CHUNK,
    PollRefused,
    _poll_loop,
    bootstrap_feed_cursor,
    build_poll_updates,
    build_solr_updates,
    collect_dirty_identifiers,
    fetch_marked_editions,
    main,
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
        "bookabc": {"key": "/books/OL1M", "root": "/works/OL1W"},
        "bookxyz": {"key": "/books/OL2M", "root": "/works/OL2W"},
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
async def test_solr_update_in_place_success_does_not_raise():
    with patch("scripts.solr_updater.loan_availability_updater.get_solr", return_value=MagicMock(spec=Solr)) as mock_get_solr:
        mock_get_solr.return_value.update_in_place_async.return_value = {"responseHeader": {"status": 0}}
        await solr_update_in_place([{"key": "/books/OL1M"}], commit=True)  # no exception


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
        with pytest.raises(RuntimeError, match="Solr in-place update error"):
            await solr_update_in_place([{"key": "/books/OL1M"}])


@pytest.mark.asyncio
async def test_solr_update_in_place_propagates_transport_errors():
    with patch("scripts.solr_updater.loan_availability_updater.get_solr", return_value=MagicMock(spec=Solr)) as mock_get_solr:
        mock_get_solr.return_value.update_in_place_async.side_effect = RuntimeError("Solr unreachable")
        with pytest.raises(RuntimeError, match="Solr unreachable"):
            await solr_update_in_place([{"key": "/books/OL1M"}])


# ---------------------------------------------------------------------------
# Shared Solr fixtures for the tests that drive a whole poll.
#
# A poll issues two kinds of select: resolve identifiers -> edition docs, and
# read back the set Solr currently has marked. _select_side_effect routes by
# query content so one mock serves both.
# ---------------------------------------------------------------------------

_RESOLVE_RESULT = MagicMock()
_RESOLVE_RESULT.docs = [{"key": "/books/OL1M", "ia": ["bookabc"], "_root_": "/works/OL1W"}]
_EMPTY_RESULT = MagicMock()
_EMPTY_RESULT.docs = []

_OK_RESPONSE = {"responseHeader": {"status": 0}}


def _select_side_effect(*args, **kwargs):
    """Route Solr select calls to the right fixture by query content."""
    query = kwargs.get("query", "") or (args[0] if args else "")
    if "ia:" in query:
        return _RESOLVE_RESULT
    # ebook_unavailable:1 → the currently-marked set (empty unless overridden)
    return _EMPTY_RESULT


# ---------------------------------------------------------------------------
# Findings from the adversarial review of the first revision
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_edition_keys_chunks_its_query():
    """A poll hands over every identifier the index says is unavailable. One
    clause per identifier against Solr's maxBooleanClauses (30000 in
    production) failed the whole query, which propagated out of the poll and
    killed the process -- so the daemon could never complete a cycle at all,
    on any run."""
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


def test_a_waitlisted_book_is_not_available():
    """The predicate both loops share. `available_to_waitlist` means you may
    join a QUEUE, not that you may read the book -- counting it as available
    here is the single edit that would break everything below."""
    assert lending.is_available_for_loan(WAITLISTED) is False
    assert lending.is_available_for_loan(AVAILABLE) is True


# ---------------------------------------------------------------------------
# Index seed + overlap replay
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Poll-and-reconcile (v3). One read of the index's unavailable set, one read of
# what Solr has marked, one bulk update carrying both directions.
#
# `resolve_edition_keys` and `fetch_marked_editions` are patched out: they have
# their own tests, and what these pin is the set arithmetic and the guard --
# which is where a defect publishes a checked-out book as borrowable.
# ---------------------------------------------------------------------------

_NOW = 2_000_000_000  # an index currency far in the future: nothing is 'too fresh' to clear

POLL_EDITIONS = {
    "bookaaa": {"key": "/books/OL1M", "root": "/works/OL1W"},
    "bookbbb": {"key": "/books/OL2M", "root": "/works/OL2W"},
    "bookccc": {"key": "/books/OL3M", "root": "/works/OL3W"},
}


def _marked(*keys: str) -> dict[str, dict]:
    """Marked editions as Solr actually returns them -- WITH a stamp.

    An unstamped doc is a real but transitional state (marked before a daemon
    that writes stamps) and the poll handles it separately, so a fixture
    without one is not a realistic marked edition. The stamp here is old enough
    to be clearable, which is what these tests are about.
    """
    by_key = {info["key"]: (ia, info) for ia, info in POLL_EDITIONS.items()}
    return {key: {"key": key, "ia": [by_key[key][0]], "_root_": by_key[key][1]["root"], "ebook_unavailable_ts": 1} for key in keys}


def _rtg(marked: dict[str, dict]):
    """Patch the real-time-get the clear path uses, echoing the snapshot back.

    The default is "nothing changed during the poll", which is what every test
    that is not ABOUT the race wants. test_a_clear_is_dropped_when_the_feed_marks_it_mid_poll
    overrides it to return a re-stamped doc.
    """
    solr = MagicMock(spec=Solr)
    solr.get_many_async = AsyncMock(return_value=list(marked.values()))
    return patch("scripts.solr_updater.loan_availability_updater.get_solr", return_value=solr)


@pytest.fixture(autouse=True)
def _ground_truth_must_be_declared():
    """Every clear is now confirmed against ground truth, so a test that lets a
    clear through has an opinion about what ground truth says -- and must state
    it rather than inherit a default.

    A permissive default would be the dangerous one: it answers "available" to
    anything, so a regression that skipped confirmation entirely would leave
    this suite green. This raises instead, and the message names the fix.
    """

    async def _undeclared(*args, **kwargs):
        raise AssertionError(
            "This test reached the ground-truth confirmation without declaring what it answers. "
            'Add patch("openlibrary.core.lending.get_availability_async", AsyncMock(return_value={...})) '
            "with AVAILABLE or UNAVAILABLE per identifier."
        )

    with patch("openlibrary.core.lending.get_availability_async", _undeclared):
        yield


def _poll(identifiers: list[str], marked: dict[str, dict]):
    resolved = {ia: POLL_EDITIONS[ia] for ia in identifiers if ia in POLL_EDITIONS}
    return (
        patch("scripts.solr_updater.loan_availability_updater.resolve_edition_keys", AsyncMock(return_value=resolved)),
        patch("scripts.solr_updater.loan_availability_updater.fetch_marked_editions", AsyncMock(return_value=marked)),
        _rtg(marked),
    )


def _free(*identifiers: str):
    """Declare that ground truth agrees these identifiers are back on the shelf.

    Required by `_ground_truth_must_be_declared` on any test that lets a clear
    through, because every clear is confirmed before it is written.
    """
    return patch("openlibrary.core.lending.get_availability_async", AsyncMock(return_value=dict.fromkeys(identifiers, AVAILABLE)))


def _sets(updates: list[dict]) -> tuple[set[str], set[str]]:
    """(keys set to unavailable, keys set to available)."""
    mark = {u["key"] for u in updates if u["ebook_unavailable"] == {"set": EBOOK_UNAVAILABLE}}
    clear = {u["key"] for u in updates if u["ebook_unavailable"] == {"set": EBOOK_AVAILABLE}}
    return mark, clear


@pytest.mark.asyncio
async def test_a_poll_marks_a_newly_unavailable_book():
    resolve, marked, rtg = _poll(["bookaaa", "bookbbb"], _marked("/books/OL1M"))
    with resolve, marked, rtg:
        updates = await build_poll_updates(["bookaaa", "bookbbb"], _NOW)
    mark, clear = _sets(updates)
    assert mark == {"/books/OL2M"}, "the book the index newly calls unavailable must be marked"
    assert clear == set(), "nothing freed up, so nothing may be cleared"
    assert all("_root_" in u for u in updates), "an in-place update on a nested child needs its parent key"


@pytest.mark.asyncio
async def test_a_poll_clears_a_book_the_index_no_longer_calls_unavailable():
    """The case the repairer used to own. The index reflects expiry directly,
    so a book dropping out of the set is a return or an expiry."""
    resolve, marked, rtg = _poll(["bookaaa"], _marked("/books/OL1M", "/books/OL2M"))
    with resolve, marked, rtg, _free("bookbbb"):
        updates = await build_poll_updates(["bookaaa"], _NOW)
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
    resolve, marked, rtg = _poll(list(POLL_EDITIONS), {})
    with resolve, marked, rtg:
        updates = await build_poll_updates(list(POLL_EDITIONS), _NOW)
    mark, clear = _sets(updates)
    assert mark == {"/books/OL1M", "/books/OL2M", "/books/OL3M"}
    assert clear == set(), "an empty marked set has nothing to clear -- and must not invent any"


@pytest.mark.asyncio
async def test_an_unchanged_poll_writes_nothing():
    """Idempotence is what makes a 30-second cadence affordable: a steady state
    costs one read and zero writes, so write volume tracks real lending churn
    rather than the poll rate."""
    resolve, marked, rtg = _poll(["bookaaa", "bookbbb"], _marked("/books/OL1M", "/books/OL2M"))
    with resolve, marked, rtg:
        updates = await build_poll_updates(["bookaaa", "bookbbb"], _NOW)
    assert updates == []


def _many_marked(n: int) -> dict[str, dict]:
    return {f"/books/OL{i}M": {"key": f"/books/OL{i}M", "ia": [f"book{i}"], "_root_": f"/works/OL{i}W", "ebook_unavailable_ts": 1} for i in range(n)}


@pytest.mark.asyncio
async def test_a_mass_clear_is_refused_when_ground_truth_says_the_books_are_still_out():
    """A degraded or mid-reindex ES returning a small-but-consistent set passes
    every other guard -- the numFound check only catches a read shorter than
    its OWN total. Here ground truth disagrees with the index, so the index is
    what is wrong, and nothing is cleared."""
    resolve, marked, rtg = _poll(["bookaaa"], _many_marked(500))
    with (
        resolve,
        marked,
        rtg,
        patch("openlibrary.core.lending.get_availability_async", AsyncMock(return_value={f"book{i}": UNAVAILABLE for i in range(500)})),
    ):
        updates = await build_poll_updates(["bookaaa"], _NOW)
    _, clear = _sets(updates)
    assert clear == set(), "ground truth contradicted the index, so no clear may proceed"


@pytest.mark.asyncio
async def test_a_genuine_mass_free_proceeds_once_ground_truth_agrees():
    """The breaker must not become a permanent refusal. A batch of same-day
    loans expiring together is indistinguishable from a collapsed index BY
    VOLUME, and if the clear set stays large every cycle, refusing on volume
    alone freezes availability until a human notices. Ground truth tells them
    apart, so the daemon recovers on its own."""
    resolve, marked, rtg = _poll(["bookaaa"], _many_marked(500))
    with (
        resolve,
        marked,
        rtg,
        patch("openlibrary.core.lending.get_availability_async", AsyncMock(return_value={f"book{i}": AVAILABLE for i in range(500)})),
    ):
        updates = await build_poll_updates(["bookaaa"], _NOW)
    _, clear = _sets(updates)
    assert len(clear) == 499, "every edition ground truth calls available must clear"
    assert "/books/OL0M" in clear


@pytest.mark.asyncio
async def test_a_mass_clear_keeps_the_editions_ground_truth_cannot_answer_for():
    """Confirmation is per-edition, not a sample promoted to a universal: an
    answer that never arrived is not an answer that said available, and the
    clear direction is the unrecoverable one."""
    answers: dict = {f"book{i}": AVAILABLE for i in range(100)}
    answers.update({f"book{i}": UNAVAILABLE for i in range(100, 200)})
    # books 200-499 get no answer at all
    resolve, marked, rtg = _poll(["bookaaa"], _many_marked(500))
    with resolve, marked, rtg, patch("openlibrary.core.lending.get_availability_async", AsyncMock(return_value=answers)):
        updates = await build_poll_updates(["bookaaa"], _NOW)
    _, clear = _sets(updates)
    # 99, not 100: the index still calls bookaaa unavailable, and bookaaa is
    # /books/OL1M, so it is never a clear candidate in the first place.
    assert len(clear) == 99, "only the editions with an explicit available answer may clear"
    assert "/books/OL1M" not in clear, "the index still calls this one out"
    assert "/books/OL150M" not in clear, "ground truth said still out"
    assert "/books/OL300M" not in clear, "no answer is not an answer"


@pytest.mark.asyncio
async def test_a_mass_clear_without_ocaids_is_refused_rather_than_assumed():
    """Ground truth is keyed by ocaid. With none to ask about, the check cannot
    run -- and a check that cannot run must not read as a check that passed."""
    no_ocaids = {f"/books/OL{i}M": {"key": f"/books/OL{i}M", "ia": [], "_root_": f"/works/OL{i}W"} for i in range(500)}
    resolve, marked, rtg = _poll([], no_ocaids)
    with resolve, marked, rtg:
        updates = await build_poll_updates([], _NOW)
    _, clear = _sets(updates)
    assert clear == set(), "ground truth could not be consulted, so no clear may proceed"


@pytest.mark.asyncio
async def test_ordinary_churn_clears_and_costs_one_bulk_request():
    """Measured 2026-10-05, a normal cycle clears 0-2 against ~766 marked. The
    whole affordability argument for confirming every clear rests on that: the
    clear set is bounded by the RETURN RATE, not by the collection, so a
    routine poll is one batched request however many books are on loan."""
    many = {f"/books/OL{i}M": {"key": f"/books/OL{i}M", "ia": [f"book{i}"], "_root_": f"/works/OL{i}W", "ebook_unavailable_ts": 1} for i in range(766)}
    still_out = [f"book{i}" for i in range(2, 766)]
    resolved = {ia: {"key": f"/books/OL{ia.removeprefix('book')}M", "root": f"/works/OL{ia.removeprefix('book')}W"} for ia in still_out}
    ground_truth = AsyncMock(return_value={"book0": AVAILABLE, "book1": AVAILABLE})
    with (
        patch("scripts.solr_updater.loan_availability_updater.resolve_edition_keys", AsyncMock(return_value=resolved)),
        patch("scripts.solr_updater.loan_availability_updater.fetch_marked_editions", AsyncMock(return_value=many)),
        _rtg(many),
        patch("openlibrary.core.lending.get_availability_async", ground_truth),
    ):
        updates = await build_poll_updates(still_out, _NOW)
    _, clear = _sets(updates)
    assert clear == {"/books/OL0M", "/books/OL1M"}, "two returns is ordinary and must go through"
    assert ground_truth.await_count == 1, "one call for the cycle"
    assert ground_truth.await_args.args[1] == ["book0", "book1"], "and it asks only about what is being cleared, not about the 766 marked"


@pytest.mark.asyncio
async def test_a_truncated_marked_read_is_refused_rather_than_treated_as_the_set():
    """An edition outside a capped read is indistinguishable from one the index
    no longer calls unavailable, and the reconcile clears on absence."""
    mock_solr = MagicMock(spec=Solr)
    mock_solr.select_async.return_value = MagicMock(docs=[{"key": f"/books/OL{i}M", "ia": [], "_root_": "/works/OL1W"} for i in range(MARKED_SET_MAX)])
    with patch("scripts.solr_updater.loan_availability_updater.get_solr", return_value=mock_solr), pytest.raises(PollRefused) as excinfo:
        await fetch_marked_editions()
    assert "cap" in str(excinfo.value)


# ---------------------------------------------------------------------------
# main() as the poll loop. One iteration, then SystemExit out of the sleep.
# ---------------------------------------------------------------------------


async def _run_poll_once(solr_mock, lending_mock, unavailable: list[str], dry_run: bool = False) -> None:
    lending_mock.get_checked_out_candidates_async = AsyncMock(return_value=unavailable)
    lending_mock.CheckedOutSeedIncomplete = CheckedOutSeedIncomplete
    with (
        patch("scripts.solr_updater.loan_availability_updater.asyncio.sleep", AsyncMock(side_effect=SystemExit)),
        pytest.raises(SystemExit),
    ):
        await _poll_loop(poll_interval=0, es_lag_margin=0, dry_run=dry_run)


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
        "scripts.solr_updater.loan_availability_updater.resolve_edition_keys", AsyncMock(return_value={"bookabc": {"key": "/books/OL1M", "root": "/works/OL1W"}})
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
        "scripts.solr_updater.loan_availability_updater.resolve_edition_keys", AsyncMock(return_value={"bookabc": {"key": "/books/OL1M", "root": "/works/OL1W"}})
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
        await _poll_loop(poll_interval=0, es_lag_margin=0, dry_run=False)

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
        "scripts.solr_updater.loan_availability_updater.resolve_edition_keys", AsyncMock(return_value={"bookabc": {"key": "/books/OL1M", "root": "/works/OL1W"}})
    ):
        await _run_poll_once(solr, mock_lending, ["bookabc"], dry_run=True)

    assert not solr.update_in_place_async.called


# ---------------------------------------------------------------------------
# Defects found by adversarial review 2026-10-06. Each test below exists
# because the thing it pins was broken and shipped, not because it seemed
# worth asserting.
# ---------------------------------------------------------------------------


def test_the_shipped_entrypoint_runs_as_a_program_not_just_as_a_function():
    """PAM #57: CI must execute the DEPLOYMENT ENTRYPOINT, not only main().

    The sibling test below compares the launcher's flags against main()'s
    signature by PARSING both. That is a static check: it would pass on a
    module that cannot be executed at all -- an import error at module scope, a
    signature FnToCLI cannot build a parser for, a missing __main__ block. The
    deployment runs `python scripts/solr_updater/loan_availability_updater.py`,
    and nothing here had ever run that.

    It matters more on this branch than on the poll-only one, because a restart
    exercises every startup path at once and this daemon now has two.

    `--help` is the cheapest invocation that crosses the whole boundary: it
    imports the module, reaches __main__, builds the FnToCLI parser from
    main()'s real signature, and renders every parameter. It needs no config,
    no Solr and no network, so it runs in ordinary CI rather than behind a
    container gate.
    """
    repo = Path(__file__).parents[3]
    entrypoint = repo / "scripts" / "solr_updater" / "loan_availability_updater.py"
    assert entrypoint.exists(), f"entrypoint not found at {entrypoint}"

    # PYTHONPATH is set to the repo root because THE DEPLOYMENT SETS IT --
    # docker/compose gives the container PYTHONPATH=/openlibrary, which is how
    # `import infogami` resolves through the repo-root symlink. Python puts the
    # SCRIPT's directory on sys.path, not the working directory, so without it
    # the entrypoint cannot import its own dependencies. Reproducing that is
    # fidelity to the deployment, not a fudge to make the test pass.
    result = subprocess.run(
        [sys.executable, str(entrypoint), "--help"],
        capture_output=True,
        text=True,
        cwd=repo,
        env={**os.environ, "PYTHONPATH": str(repo)},
        timeout=120,
        check=False,  # the exit code IS the assertion below
    )
    assert result.returncode == 0, f"the shipped entrypoint exits {result.returncode} when run as a program:\n{result.stderr[-2000:]}"

    # Every parameter main() takes must reach the CLI. A parameter FnToCLI
    # silently drops is a flag the launcher could pass and the program ignore.
    for flag in ("--poll-interval", "--feed-interval", "--es-lag-margin", "--dry-run"):
        assert flag in result.stdout, f"{flag} is in main()'s signature but not in the program's own --help"


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
    a quiet route that stays under the breaker's threshold."""
    mock_solr = MagicMock(spec=Solr)
    result = MagicMock(docs=[{"key": "/books/OL1M", "ia": ["bookaaa"], "_root_": "/works/OL1W"}], num_found=500, response_header={})
    mock_solr.select_async.return_value = result
    with patch("scripts.solr_updater.loan_availability_updater.get_solr", return_value=mock_solr), pytest.raises(PollRefused) as excinfo:
        await fetch_marked_editions()
    assert "500" in str(excinfo.value)


@pytest.mark.asyncio
async def test_a_partial_solr_read_is_refused_rather_than_cleared():
    """`partialResults` is the only signal that `timeAllowed` tripped; numFound
    can look consistent with the short list it returned."""
    mock_solr = MagicMock(spec=Solr)
    result = MagicMock(docs=[{"key": "/books/OL1M", "ia": ["bookaaa"], "_root_": "/works/OL1W"}], num_found=1, response_header={"partialResults": True})
    mock_solr.select_async.return_value = result
    with patch("scripts.solr_updater.loan_availability_updater.get_solr", return_value=mock_solr), pytest.raises(PollRefused) as excinfo:
        await fetch_marked_editions()
    assert "partialResults" in str(excinfo.value)


@pytest.mark.asyncio
async def test_a_refused_mass_clear_still_marks_the_newly_unavailable():
    """Holding the marks alongside a refused clear reaches the unrecoverable
    failure from the other side: while the index is degraded, real borrows keep
    happening and nothing records them, so checked-out books are published as
    borrowable for the length of the outage. Marking needs no confirmation."""
    marked = {f"/books/OL{i}M": {"key": f"/books/OL{i}M", "ia": [f"book{i}"], "_root_": f"/works/OL{i}W", "ebook_unavailable_ts": 1} for i in range(500)}
    resolved = {"bookaaa": {"key": "/books/OL9001M", "root": "/works/OL9001W"}}
    with (
        patch("scripts.solr_updater.loan_availability_updater.resolve_edition_keys", AsyncMock(return_value=resolved)),
        patch("scripts.solr_updater.loan_availability_updater.fetch_marked_editions", AsyncMock(return_value=marked)),
        _rtg(marked),
        # Ground truth says every candidate clear is still checked out: the
        # index is wrong, so no clear may proceed.
        patch("openlibrary.core.lending.get_availability_async", AsyncMock(return_value={f"book{i}": UNAVAILABLE for i in range(500)})),
    ):
        updates = await build_poll_updates(["bookaaa"], _NOW)
    mark, clear = _sets(updates)
    assert mark == {"/books/OL9001M"}, "a newly-unavailable book must still be marked"
    assert clear == set(), "no clear may proceed when ground truth contradicts the index"


# ---------------------------------------------------------------------------
# The hybrid's seams. Each of these exists because the wiring between two
# correct pieces is where this design can go wrong -- the restored follower and
# the poll were both already tested; what was not was them disagreeing.
# ---------------------------------------------------------------------------

_HOUR = 3600
_MARKED_RECENTLY = 1_000_000_000
_EDITION = {"key": "/books/OL1M", "root": "/works/OL1W"}


def _marked_doc(marked_at: int | None) -> dict[str, dict]:
    doc: dict = {"key": "/books/OL1M", "ia": ["bookaaa"], "_root_": "/works/OL1W"}
    if marked_at is not None:
        doc["ebook_unavailable_ts"] = marked_at
    return {"/books/OL1M": doc}


async def _poll_against(index_says: list[str], marked: dict, index_current_as_of: int, free: tuple[str, ...] = ()) -> tuple[set, set]:
    """`free` names the identifiers ground truth will confirm as available.

    Left empty deliberately: a caller that expects NO clear should not declare
    one, so if the gate ever stops holding, the strict fixture turns it into a
    failure rather than letting it through on a permissive default.
    """
    resolved = {"bookaaa": _EDITION} if "bookaaa" in index_says else {}
    with contextlib.ExitStack() as stack:
        stack.enter_context(patch("scripts.solr_updater.loan_availability_updater.resolve_edition_keys", AsyncMock(return_value=resolved)))
        stack.enter_context(patch("scripts.solr_updater.loan_availability_updater.fetch_marked_editions", AsyncMock(return_value=marked)))
        stack.enter_context(_rtg(marked))
        if free:
            stack.enter_context(_free(*free))
        return _sets(await build_poll_updates(index_says, index_current_as_of))


@pytest.mark.asyncio
@pytest.mark.parametrize("margin_hours", [1, 6, 24, 72])
async def test_the_gate_holds_a_mark_the_index_is_too_stale_to_contradict(margin_hours):
    """THE SEAM. The feed marked a borrow; the index has not seen it yet, so the
    book is absent from the unavailable set. Absence must not read as "returned".

    The margin is SWEPT rather than fixed, and that is the point of the test
    rather than thoroughness: a margin that is silently ignored -- which is a
    bug this code actually had, where the parameter was cancelled out by
    arithmetic and the module constant was used instead -- passes any test that
    holds the margin constant. Varying it is what makes the parameter
    observable.
    """
    index_current_as_of = _MARKED_RECENTLY - margin_hours * _HOUR
    mark, clear = await _poll_against([], _marked_doc(_MARKED_RECENTLY), index_current_as_of)
    assert clear == set(), f"a mark {margin_hours}h newer than the index's currency must not be cleared"
    assert mark == set()


@pytest.mark.asyncio
@pytest.mark.parametrize("age_hours", [2, 25, 100])
async def test_the_gate_clears_a_mark_older_than_the_index_currency(age_hours):
    """The boundary, and it matters as much as the gate: a guard that blocks
    everything looks identical to a guard that works, until a book is never
    freed. A mark older than the index's currency IS cleared."""
    index_current_as_of = _MARKED_RECENTLY + _HOUR
    marked_at = _MARKED_RECENTLY - age_hours * _HOUR
    _, clear = await _poll_against([], _marked_doc(marked_at), index_current_as_of, free=("bookaaa",))
    assert clear == {"/books/OL1M"}, f"a mark {age_hours}h older than the index's currency must be cleared"


@pytest.mark.asyncio
async def test_a_poll_mark_carries_a_timestamp_so_the_next_poll_cannot_clear_it():
    """Marks from the POLL need the stamp as much as marks from the feed --
    without it the next poll reads epoch 0 and is free to clear immediately."""
    mark, _ = await _poll_against(["bookaaa"], {}, _MARKED_RECENTLY)
    assert mark == {"/books/OL1M"}
    with (
        patch("scripts.solr_updater.loan_availability_updater.resolve_edition_keys", AsyncMock(return_value={"bookaaa": _EDITION})),
        patch("scripts.solr_updater.loan_availability_updater.fetch_marked_editions", AsyncMock(return_value={})),
        _free("bookaaa"),
    ):
        updates = await build_poll_updates(["bookaaa"], _MARKED_RECENTLY)

    # ONE write carrying BOTH fields, not two writes. #12689 pinned this and
    # the equivalence was nearly lost here: reading the stamp off updates[0]
    # without bounding the update COUNT let a second, stamp-less write for the
    # same edition through all 59 tests. The hazard is ordering -- a mark and
    # its stamp landing separately can interleave with a clear, and the gate
    # then judges an edition whose stamp belongs to a different write.
    assert len(updates) == 1, "a mark and its stamp must arrive as one update, not two"
    assert updates[0]["ebook_unavailable"] == {"set": EBOOK_UNAVAILABLE}, "and the mark must be on that same update"
    ts = updates[0]["ebook_unavailable_ts"]["set"]
    # Bounded against the clock, not "> 0". A review of #12689 proved the loose
    # form green against both a milliseconds mutation and a frozen constant --
    # and here either is worse than there, because this gate COMPARES the stamp
    # against a wall-clock currency. A ms stamp is always greater, so no clear
    # would ever proceed and availability would freeze.
    now = int(time.time())
    assert now - 5 <= ts <= now + 5, f"ts={ts} is not epoch SECONDS near now ({now})"


def test_a_feed_mark_is_stamped_with_the_event_time_not_the_read_time():
    """A batch read at 10:00 can carry an event from 09:58. Stamping it 10:00
    would claim two minutes of protection the mark has not earned."""
    rows = [{"identifier": "bookaaa", "uid": 5, "event_type": "borrow", "extra": "{}", "time": "2001-09-09 01:46:40"}]
    dirty = collect_dirty_identifiers(rows)
    updates = build_solr_updates(dirty, {"bookaaa": _EDITION})
    assert updates[0]["ebook_unavailable_ts"]["set"] == _MARKED_RECENTLY


def test_a_feed_mark_with_an_unreadable_time_falls_back_to_now():
    """Over-protect by seconds rather than under-protect: an unparsable row must
    not produce a mark stamped epoch 0, which the next poll would clear."""
    rows = [{"identifier": "bookaaa", "uid": 5, "event_type": "borrow", "extra": "{}", "time": "not-a-date"}]
    updates = build_solr_updates(collect_dirty_identifiers(rows), {"bookaaa": _EDITION})
    assert updates[0]["ebook_unavailable_ts"]["set"] > _MARKED_RECENTLY


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("margin", "expect_cleared"),
    [
        (10, True),  # the index's currency is well past the mark: clear it
        (10_000_000, False),  # the margin reaches back before the mark: hold it
    ],
)
async def test_the_margin_parameter_reaches_the_gate(margin, expect_cleared):
    """Exercises _poll_loop, not build_poll_updates, and that is the entire point.

    An earlier revision computed the currency as
    `poll_started_at - es_lag_margin + ES_LAG_MARGIN`, which cancels out: the
    --es-lag-margin flag was silently ignored in favour of the module constant.
    A flag a tool quietly ignores is worse than one it rejects, because the
    operator believes they have changed something.

    The first attempt at covering this swept the margin in tests that called
    build_poll_updates DIRECTLY with an already-computed currency -- so they
    never executed the conversion where the bug lived, and the mutation
    survived all of them. Verified: re-introducing the cancelled arithmetic
    leaves those sweeps green and reddens only this test. The margin has to
    enter through the same door the operator's flag does.
    """
    marked = {"/books/OL1M": {"key": "/books/OL1M", "ia": ["bookaaa"], "_root_": "/works/OL1W", "ebook_unavailable_ts": int(time.time()) - 1000}}
    solr = MagicMock(spec=Solr)
    solr.update_in_place_async.return_value = _OK_RESPONSE
    written: list[dict] = []

    async def capture(request, commit=False):
        written.extend(request)

    with (
        patch("scripts.solr_updater.loan_availability_updater.get_solr", return_value=solr),
        patch("scripts.solr_updater.loan_availability_updater.resolve_edition_keys", AsyncMock(return_value={})),
        patch("scripts.solr_updater.loan_availability_updater.fetch_marked_editions", AsyncMock(return_value=marked)),
        _rtg(marked),
        patch("scripts.solr_updater.loan_availability_updater.solr_update_in_place", AsyncMock(side_effect=capture)),
        patch("openlibrary.core.lending.get_checked_out_candidates_async", AsyncMock(return_value=[])),
        _free("bookaaa"),
        patch("scripts.solr_updater.loan_availability_updater.asyncio.sleep", AsyncMock(side_effect=SystemExit)),
        pytest.raises(SystemExit),
    ):
        await _poll_loop(poll_interval=0, es_lag_margin=margin, dry_run=False)

    cleared = [u for u in written if u.get("ebook_unavailable") == {"set": EBOOK_AVAILABLE}]
    assert bool(cleared) is expect_cleared, f"margin={margin} should {'clear' if expect_cleared else 'hold'} a mark 1000s old"


# ---------------------------------------------------------------------------
# The cursor bootstrap. The follower exists to cover one gap -- borrows the
# index has not seen -- so it must START at the index's currency. Too far back
# replays days to no purpose; too far forward leaves the gap open until the
# next borrow.
# ---------------------------------------------------------------------------


def _feed_response(rows: list[dict], latest_uid: int | None = None) -> dict:
    return {"status": "OK", "latest_uid": latest_uid if latest_uid is not None else (rows[-1]["uid"] if rows else 0), "rows": rows}


def _row(uid: int, epoch: int) -> dict:
    stamp = datetime.datetime.fromtimestamp(epoch, datetime.UTC).strftime("%Y-%m-%d %H:%M:%S")
    return {"identifier": f"book{uid}", "uid": uid, "event_type": "borrow", "extra": "{}", "time": stamp}


@pytest.mark.asyncio
async def test_the_bootstrap_starts_at_the_index_currency_not_the_feed_head():
    """THE SEAM. The cursor must land on the last event the index can be assumed
    to know about, so the follower replays exactly the lag gap."""
    now = int(time.time())
    margin = 3600
    # uids 1..5 at hourly steps; the index's currency is now-3600, so events
    # older than that are already reflected and 3 is the last of them.
    rows = [_row(1, now - 10800), _row(2, now - 7200), _row(3, now - 5400), _row(4, now - 1800), _row(5, now - 60)]
    with patch("openlibrary.core.lending.get_loan_changes", AsyncMock(return_value=_feed_response(rows))):
        cursor = await bootstrap_feed_cursor(margin)
    assert cursor == 3, "the cursor must sit at the newest event the index already knows about"


@pytest.mark.asyncio
async def test_the_bootstrap_lands_inside_a_full_window_at_neither_end():
    """Both ends of a full day of events are wrong, and for opposite reasons.
    Starting at the oldest row is safe but wasteful -- it re-marks, every
    restart, books the index already covers. Starting at the head replays
    NOTHING, which is the unsafe end: the lag gap stays uncovered until the
    next borrow. So this bounds the cursor on both sides and then pins it
    exactly, because `cursor > 1` alone is satisfied by the head."""
    now = int(time.time())
    # 59 events spread across a day at 24-minute steps, with the index current
    # as of an hour ago. uid 57 sits at now-4320 and uid 58 at now-2880, so the
    # last event the index can be assumed to know about is 57.
    rows = [_row(i, now - 86_400 + i * 1440) for i in range(1, 60)]
    oldest, head = rows[0]["uid"], rows[-1]["uid"]
    with patch("openlibrary.core.lending.get_loan_changes", AsyncMock(return_value=_feed_response(rows))):
        cursor = await bootstrap_feed_cursor(3600)
    assert cursor > oldest, "the cursor must not fall back to the start of the window and replay the whole day"
    assert cursor < head, "the cursor must not land on the head, which replays nothing and leaves the lag gap uncovered"
    assert cursor == 57, "the cursor must sit at the newest event the index already knows about"


@pytest.mark.asyncio
async def test_a_feed_window_too_short_bootstraps_at_its_oldest_row_and_says_so(caplog):
    """The window does not reach back as far as the index's currency, so part of
    the lag gap cannot be covered at all. Starting at the oldest row covers as
    much as the feed will show -- and the shortfall is LOGGED rather than
    silently accepted, because an uncovered gap looks exactly like a healthy
    daemon."""
    now = int(time.time())
    rows = [_row(90, now - 120), _row(91, now - 60), _row(92, now - 30)]
    with (
        patch("openlibrary.core.lending.get_loan_changes", AsyncMock(return_value=_feed_response(rows))),
        caplog.at_level(logging.WARNING),
    ):
        cursor = await bootstrap_feed_cursor(86_400)
    assert cursor == 90, "with nothing old enough, start at the oldest row the window shows"
    assert "uncovered" in caplog.text.lower()


@pytest.mark.asyncio
async def test_an_empty_feed_falls_back_to_the_head_and_says_so(caplog):
    """Degrades to 'the gap is uncovered until the next borrow' rather than to
    anything unsafe -- and says which."""
    with (
        patch("openlibrary.core.lending.get_loan_changes", AsyncMock(return_value=_feed_response([], latest_uid=777))),
        caplog.at_level(logging.WARNING),
    ):
        cursor = await bootstrap_feed_cursor(3600)
    assert cursor == 777
    assert "uncovered" in caplog.text.lower()


@pytest.mark.asyncio
async def test_a_mark_with_no_stamp_is_neither_cleared_nor_left_unknown():
    """The third state. An edition marked before a daemon that writes stamps
    has no stamp, and BOTH obvious defaults are wrong: read it as 0 and the gate
    clears a mark that might be recent, publishing a checked-out book as
    borrowable with no event to follow until the loan ends; read it as now and
    nothing ever clears it OR stamps it, so the book is hidden forever.

    So the poll stamps it instead of judging it: no clear this cycle, a known
    and conservative age from the next one.
    """
    resolve, marked, rtg = _poll([], _marked_doc(None))
    with resolve, marked, rtg:
        updates = await build_poll_updates([], _MARKED_RECENTLY)
    mark, clear = _sets(updates)
    assert clear == set(), "an unknown age must not be resolved by clearing"
    assert mark == {"/books/OL1M"}, "it must be stamped, or it stays unknown forever"
    assert updates[0]["ebook_unavailable_ts"]["set"] > 0


@pytest.mark.asyncio
async def test_a_stamped_mark_is_still_judged_normally_afterwards():
    """The stamp must not become permanent protection -- that is the failure
    mode of reading absent as 'now'. One margin later the ordinary rule applies."""
    resolve, marked, rtg = _poll([], _marked_doc(_MARKED_RECENTLY - 100_000))
    with resolve, marked, rtg, _free("bookaaa"):
        updates = await build_poll_updates([], _MARKED_RECENTLY)
    _, clear = _sets(updates)
    assert clear == {"/books/OL1M"}


@pytest.mark.asyncio
async def test_the_breaker_is_sized_against_what_the_index_dropped():
    """The gate filters `to_clear` before the breaker measures it, so sizing
    the threshold against the whole marked set lowered the numerator and left
    the denominator alone -- a degraded index could drop hundreds, have most
    held as too fresh, and slip the rest through a threshold computed as though
    nothing had been held.

    Here the index drops 300 of 1000 marked. 280 are too fresh to clear, 20 are
    not. Against `len(marked)` the limit is 100 and 20 sails through with no
    ground-truth call; against the 300 it actually dropped the limit is 30, so
    20 still passes -- but the shape is now proportional to the event rather
    than to the collection.
    """
    fresh, old_ = 280, 20
    marked = {}
    for i in range(1000):
        stamp = _MARKED_RECENTLY if i < fresh else 1
        marked[f"/books/OL{i}M"] = {"key": f"/books/OL{i}M", "ia": [f"book{i}"], "_root_": f"/works/OL{i}W", "ebook_unavailable_ts": stamp}
    # The index still calls everything from 300 up unavailable; it dropped 0-299.
    resolved = {f"book{i}": {"key": f"/books/OL{i}M", "root": f"/works/OL{i}W"} for i in range(300, 1000)}
    with (
        patch("scripts.solr_updater.loan_availability_updater.resolve_edition_keys", AsyncMock(return_value=resolved)),
        patch("scripts.solr_updater.loan_availability_updater.fetch_marked_editions", AsyncMock(return_value=marked)),
        _rtg(marked),
        patch("openlibrary.core.lending.get_availability_async", AsyncMock(return_value={f"book{i}": AVAILABLE for i in range(1000)})),
    ):
        updates = await build_poll_updates([f"book{i}" for i in range(300, 1000)], _MARKED_RECENTLY - 1)
    _, clear = _sets(updates)
    assert len(clear) == old_, "only the marks old enough to judge may clear"
    assert "/books/OL0M" not in clear, "a fresh mark must never clear regardless of the breaker"


@pytest.mark.asyncio
async def test_a_truncated_edition_resolve_is_refused_rather_than_cleared():
    """The other half of the comparison that turns absence into a clear.

    `fetch_marked_editions` had this guard and `resolve_edition_keys` did not,
    even though an identifier that fails to resolve is indistinguishable from
    one the index no longer calls unavailable. A Solr slowdown tripping
    `timeAllowed` returns HTTP 200 with a short `docs` list and
    `partialResults`, and without this the editions that fell off the end are
    cleared -- checked-out books published as borrowable, under the breaker's
    threshold, with nothing above INFO in the log. It needs a slow Solr, not an
    index incident, which is what makes it the likeliest path in the file.
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
async def test_a_clear_does_not_touch_the_timestamp():
    """`requireInPlace` cannot set a field to null, so a clear leaves the old
    value behind -- and this branch's prose leans on that: a cleared edition
    keeps the stamp of a mark it no longer has, which is harmless only because
    the stamp is read for exactly one purpose (is this MARKED edition old
    enough to clear?) and a re-mark overwrites it.

    If a clear ever started writing the stamp, that reasoning quietly stops
    holding. So the invariant is pinned rather than described.
    """
    resolve, marked, rtg = _poll([], _marked("/books/OL1M"))
    with resolve, marked, rtg, _free("bookaaa"):
        updates = await build_poll_updates([], _NOW)
    assert len(updates) == 1
    assert updates[0]["ebook_unavailable"] == {"set": EBOOK_AVAILABLE}
    assert "ebook_unavailable_ts" not in updates[0], "a clear must not write the stamp, in either direction"


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
    assert resolved == {"bookaaa": {"key": "/books/OL1M", "root": "/works/OL1W"}}


@pytest.mark.asyncio
async def test_more_editions_than_identifiers_is_not_mistaken_for_a_truncated_read():
    """The other direction of the same distinction, and the one that would halt
    the daemon rather than silently clear.

    Two editions can share an ocaid, so a chunk of 2 identifiers legitimately
    matches 3 documents. A guard comparing `num_found` against the number of
    IDENTIFIERS requested -- rather than against the documents returned -- reads
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


@pytest.mark.asyncio
async def test_a_partial_edition_resolve_is_refused_rather_than_cleared():
    """`partialResults` is the only signal that `timeAllowed` cut the query
    short; numFound can look perfectly consistent with the short list."""
    mock_solr = MagicMock(spec=Solr)
    mock_solr.select_async.return_value = MagicMock(
        docs=[{"key": "/books/OL1M", "ia": ["bookaaa"], "_root_": "/works/OL1W"}],
        num_found=1,
        response_header={"partialResults": True},
    )
    with patch("scripts.solr_updater.loan_availability_updater.get_solr", return_value=mock_solr), pytest.raises(PollRefused):
        await resolve_edition_keys(["bookaaa"])


@pytest.mark.asyncio
async def test_an_availability_outage_holds_every_clear_and_says_so_loudly(caplog):
    """A held clear is invisible by construction -- nothing is written -- so an
    availability outage looks exactly like a quiet collection: the daemon keeps
    polling, keeps marking, logs its ordinary INFO line, and availability stops
    moving for the duration. Confirming every clear is what put the service on
    this path, so the freeze it can cause has to be said out loud.

    The two causes must also be distinguishable in the message. "Ground truth
    says still out" is a degraded INDEX; "nobody answered" is an outage of the
    availability service. Investigating one as the other wastes the outage.
    """
    marked = {f"/books/OL{i}M": {"key": f"/books/OL{i}M", "ia": [f"book{i}"], "_root_": f"/works/OL{i}W", "ebook_unavailable_ts": 1} for i in range(3)}
    # What a failed batch actually returns: an error status per identifier,
    # plus the top-level key. Not a missing entry.
    outage = {f"book{i}": {"status": "error", "identifier": f"book{i}"} for i in range(3)}
    outage["error"] = "request_timeout"
    with (
        patch("scripts.solr_updater.loan_availability_updater.resolve_edition_keys", AsyncMock(return_value={})),
        patch("scripts.solr_updater.loan_availability_updater.fetch_marked_editions", AsyncMock(return_value=marked)),
        _rtg(marked),
        patch("openlibrary.core.lending.get_availability_async", AsyncMock(return_value=outage)),
        caplog.at_level(logging.ERROR, logger="openlibrary.loan-availability-updater"),
    ):
        updates = await build_poll_updates([], _NOW)
    _, clear = _sets(updates)
    assert clear == set(), "an unanswered identifier keeps its mark"
    assert "0 of 3 identifiers" in caplog.text, "the count of unanswered identifiers must be stated"
    assert "outage rather than a disagreement" in caplog.text, "and the cause must be named, not left to be inferred"


@pytest.mark.asyncio
async def test_a_degraded_index_is_reported_as_disagreement_not_as_an_outage(caplog):
    """The control for the test above: the service IS answering, and answering
    'still out'. Same held clears, different cause, and the message has to
    distinguish them or an index incident gets investigated as an outage."""
    marked = {f"/books/OL{i}M": {"key": f"/books/OL{i}M", "ia": [f"book{i}"], "_root_": f"/works/OL{i}W", "ebook_unavailable_ts": 1} for i in range(3)}
    with (
        patch("scripts.solr_updater.loan_availability_updater.resolve_edition_keys", AsyncMock(return_value={})),
        patch("scripts.solr_updater.loan_availability_updater.fetch_marked_editions", AsyncMock(return_value=marked)),
        _rtg(marked),
        patch("openlibrary.core.lending.get_availability_async", AsyncMock(return_value={f"book{i}": UNAVAILABLE for i in range(3)})),
        caplog.at_level(logging.ERROR, logger="openlibrary.loan-availability-updater"),
    ):
        updates = await build_poll_updates([], _NOW)
    _, clear = _sets(updates)
    assert clear == set()
    assert "ground truth disagreed with the index" in caplog.text
    assert "outage rather than a disagreement" not in caplog.text, "the service answered, so this is not an outage"
    assert "identifiers;" not in caplog.text, "and nothing went unanswered, so no unanswered-count line"


@pytest.mark.asyncio
@pytest.mark.parametrize("dropped_per_poll", [1, 24, 25])
async def test_a_sustained_sub_threshold_drain_is_confirmed_rather_than_metered(dropped_per_poll):
    """cq #27. The hole the old breaker left, and the reason it is gone.

    The threshold version confirmed a clear set only when it exceeded
    `max(25, 10% of the editions the index dropped)`. Below 250 dropped the
    10% never bound, so the absolute 25 WAS the guard -- and it was a per-poll
    allowance with no memory, against a poll that runs every 15 seconds. An
    index degraded such that it dropped 24 identifiers per cycle therefore
    never tripped it and never made a single ground-truth call. Against the
    measured 766-edition marked set that is 31 polls -- 465 seconds -- to clear
    the whole thing unconfirmed, 25 at a time, with nothing above INFO logged.

    A per-poll ceiling does not rate-limit a sustained drain. It meters it.

    So this stages exactly that shape: a steady sub-threshold drop where ground
    truth says every one of those books is still checked out. 1 is ordinary
    churn, 24 is the drain that used to sail through, 25 is the boundary. All
    three must now be held, because volume no longer decides anything.
    """
    marked = {f"/books/OL{i}M": {"key": f"/books/OL{i}M", "ia": [f"book{i}"], "_root_": f"/works/OL{i}W", "ebook_unavailable_ts": 1} for i in range(766)}
    # The index has stopped listing the first `dropped_per_poll` identifiers.
    still_listed = [f"book{i}" for i in range(dropped_per_poll, 766)]
    resolved = {ia: {"key": f"/books/OL{ia.removeprefix('book')}M", "root": f"/works/OL{ia.removeprefix('book')}W"} for ia in still_listed}
    ground_truth = AsyncMock(return_value={f"book{i}": UNAVAILABLE for i in range(dropped_per_poll)})
    with (
        patch("scripts.solr_updater.loan_availability_updater.resolve_edition_keys", AsyncMock(return_value=resolved)),
        patch("scripts.solr_updater.loan_availability_updater.fetch_marked_editions", AsyncMock(return_value=marked)),
        _rtg(marked),
        patch("openlibrary.core.lending.get_availability_async", ground_truth),
    ):
        updates = await build_poll_updates(still_listed, _NOW)
    _, clear = _sets(updates)
    # Consequence first, mechanism second: the failure that matters is books
    # being published as borrowable while they are out, not a missing call.
    assert clear == set(), f"ground truth says all {dropped_per_poll} are still checked out, so none may clear"
    assert ground_truth.await_count == 1, f"a {dropped_per_poll}-edition drop must be confirmed, not waved through on its size"


@pytest.mark.asyncio
async def test_the_breaker_threshold_tracks_the_drop_not_the_collection():
    """Sized against the whole marked set, a threshold scales with how many
    books are on loan rather than with how many the index just dropped -- so a
    big collection buys a big allowance for a small, wrong drop.

    1000 marked, the index drops 100, 50 of those are old enough to judge.
    Against the collection the limit is 100 and all 50 clear with no
    ground-truth call. Against the drop it is 25, the breaker trips, ground
    truth is asked, and it says the books are still out -- so none clear.
    """
    marked = {
        f"/books/OL{i}M": {"key": f"/books/OL{i}M", "ia": [f"book{i}"], "_root_": f"/works/OL{i}W", "ebook_unavailable_ts": (1 if i < 50 else _MARKED_RECENTLY)}
        for i in range(1000)
    }
    resolved = {f"book{i}": {"key": f"/books/OL{i}M", "root": f"/works/OL{i}W"} for i in range(100, 1000)}
    with (
        patch("scripts.solr_updater.loan_availability_updater.resolve_edition_keys", AsyncMock(return_value=resolved)),
        patch("scripts.solr_updater.loan_availability_updater.fetch_marked_editions", AsyncMock(return_value=marked)),
        _rtg(marked),
        patch("openlibrary.core.lending.get_availability_async", AsyncMock(return_value={f"book{i}": UNAVAILABLE for i in range(1000)})),
    ):
        updates = await build_poll_updates([f"book{i}" for i in range(100, 1000)], _MARKED_RECENTLY - 1)
    _, clear = _sets(updates)
    assert clear == set(), "the breaker must trip on the drop's size and ground truth must then hold every clear"


@pytest.mark.asyncio
async def test_a_clear_is_dropped_when_the_feed_marks_it_during_the_poll():
    """H3. The poll decides to clear from a snapshot and writes seconds later,
    while the feed loop is writing to the same editions throughout.

    A book returned days ago is legitimately clearable. It is RE-BORROWED
    mid-poll; the feed stamps it. Without a re-check the poll's already-decided
    clear lands on top and publishes a checked-out book as borrowable, and
    nothing revisits it until the index notices the new borrow — a lag window
    away. That is the unrecoverable direction.

    The re-check goes through Solr's real-time get, which is the point: the
    feed writes with `commit=False`, so a searcher-based read would miss
    exactly the marks most likely to be racing.
    """
    stale = {"key": "/books/OL1M", "ia": ["bookaaa"], "_root_": "/works/OL1W", "ebook_unavailable_ts": 1}
    reborrowed = dict(stale, ebook_unavailable_ts=_MARKED_RECENTLY)

    solr = MagicMock(spec=Solr)
    solr.get_many_async = AsyncMock(return_value=[reborrowed])  # what Solr holds NOW
    with (
        patch("scripts.solr_updater.loan_availability_updater.resolve_edition_keys", AsyncMock(return_value={})),
        patch("scripts.solr_updater.loan_availability_updater.fetch_marked_editions", AsyncMock(return_value={"/books/OL1M": stale})),
        patch("scripts.solr_updater.loan_availability_updater.get_solr", return_value=solr),
        # Ground truth AGREES the book is free, so the clear survives
        # confirmation and the re-read is what drops it. Were ground truth to
        # say "still out", this would pass for the wrong reason.
        _free("bookaaa"),
    ):
        updates = await build_poll_updates([], _MARKED_RECENTLY - 1)
    _, clear = _sets(updates)
    assert clear == set(), "a clear overtaken by a fresh mark must be dropped, not written"


@pytest.mark.asyncio
async def test_a_clear_is_dropped_when_the_edition_vanished_mid_poll():
    """A reindex between the two reads. There is nothing to clear, and writing
    to a document that no longer exists at that `_root_` would 400 under
    requireInPlace and abort the whole batch — taking the other marks and
    clears with it."""
    stale = {"key": "/books/OL1M", "ia": ["bookaaa"], "_root_": "/works/OL1W", "ebook_unavailable_ts": 1}
    solr = MagicMock(spec=Solr)
    solr.get_many_async = AsyncMock(return_value=[])
    with (
        patch("scripts.solr_updater.loan_availability_updater.resolve_edition_keys", AsyncMock(return_value={})),
        patch("scripts.solr_updater.loan_availability_updater.fetch_marked_editions", AsyncMock(return_value={"/books/OL1M": stale})),
        patch("scripts.solr_updater.loan_availability_updater.get_solr", return_value=solr),
        _free("bookaaa"),
    ):
        updates = await build_poll_updates([], _MARKED_RECENTLY - 1)
    assert updates == []
