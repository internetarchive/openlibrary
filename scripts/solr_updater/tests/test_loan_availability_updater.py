"""Tests for loan_availability_updater.py"""

import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from openlibrary.core import lending
from openlibrary.core.lending import CheckedOutSeedIncomplete
from openlibrary.utils.solr import Solr
from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI
from scripts.solr_updater.loan_availability_updater import (
    CLEAR_BREAKER_FLOOR,
    CLEAR_BREAKER_FRACTION,
    EBOOK_AVAILABLE,
    EBOOK_UNAVAILABLE,
    MARKED_SET_MAX,
    SOLR_QUERY_CHUNK,
    PollRefused,
    _poll_loop,
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


def _wire_lending(lending_mock, first_batch_rows, availability=None):
    """Give the patched lending module realistic behaviour for main()."""
    lending_mock.get_loan_changes = AsyncMock(
        side_effect=[
            {"status": "OK", "rows": first_batch_rows, "latest_uid": 100},
            SystemExit(0),  # stop the loop on the second iteration
        ]
    )
    lending_mock.get_availability_async = AsyncMock(return_value={"bookabc": AVAILABLE} if availability is None else availability)
    lending_mock.is_available_for_loan.side_effect = lambda a: bool(a.get("available_to_browse") or a.get("available_to_borrow"))


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
    by_key = {info["key"]: (ia, info) for ia, info in POLL_EDITIONS.items()}
    return {key: {"key": key, "ia": [by_key[key][0]], "_root_": by_key[key][1]["root"]} for key in keys}


def _poll(identifiers: list[str], marked: dict[str, dict]):
    resolved = {ia: POLL_EDITIONS[ia] for ia in identifiers if ia in POLL_EDITIONS}
    return (
        patch("scripts.solr_updater.loan_availability_updater.resolve_edition_keys", AsyncMock(return_value=resolved)),
        patch("scripts.solr_updater.loan_availability_updater.fetch_marked_editions", AsyncMock(return_value=marked)),
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
        updates = await build_poll_updates(["bookaaa", "bookbbb"], _NOW)
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
    resolve, marked = _poll(list(POLL_EDITIONS), {})
    with resolve, marked:
        updates = await build_poll_updates(list(POLL_EDITIONS), _NOW)
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
        updates = await build_poll_updates(["bookaaa", "bookbbb"], _NOW)
    assert updates == []


def _many_marked(n: int) -> dict[str, dict]:
    return {f"/books/OL{i}M": {"key": f"/books/OL{i}M", "ia": [f"book{i}"], "_root_": f"/works/OL{i}W"} for i in range(n)}


@pytest.mark.asyncio
async def test_a_mass_clear_is_refused_when_ground_truth_says_the_books_are_still_out():
    """A degraded or mid-reindex ES returning a small-but-consistent set passes
    every other guard -- the numFound check only catches a read shorter than
    its OWN total. Here ground truth disagrees with the index, so the index is
    what is wrong, and nothing is cleared."""
    resolve, marked = _poll(["bookaaa"], _many_marked(500))
    with (
        resolve,
        marked,
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
    resolve, marked = _poll(["bookaaa"], _many_marked(500))
    with (
        resolve,
        marked,
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
    resolve, marked = _poll(["bookaaa"], _many_marked(500))
    with resolve, marked, patch("openlibrary.core.lending.get_availability_async", AsyncMock(return_value=answers)):
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
    resolve, marked = _poll([], no_ocaids)
    with resolve, marked:
        updates = await build_poll_updates([], _NOW)
    _, clear = _sets(updates)
    assert clear == set(), "ground truth could not be consulted, so no clear may proceed"


@pytest.mark.asyncio
async def test_the_breaker_does_not_trip_on_ordinary_churn():
    """Measured 2026-10-05, a normal cycle clears 0-2 against ~766 marked --
    under 1%. A guard that fires in ordinary operation gets routed around."""
    many = {f"/books/OL{i}M": {"key": f"/books/OL{i}M", "ia": [f"book{i}"], "_root_": f"/works/OL{i}W"} for i in range(766)}
    still_out = [f"book{i}" for i in range(2, 766)]
    resolved = {ia: {"key": f"/books/OL{ia.removeprefix('book')}M", "root": f"/works/OL{ia.removeprefix('book')}W"} for ia in still_out}
    with (
        patch("scripts.solr_updater.loan_availability_updater.resolve_edition_keys", AsyncMock(return_value=resolved)),
        patch("scripts.solr_updater.loan_availability_updater.fetch_marked_editions", AsyncMock(return_value=many)),
    ):
        updates = await build_poll_updates(still_out, _NOW)
    _, clear = _sets(updates)
    assert clear == {"/books/OL0M", "/books/OL1M"}, "two returns is ordinary and must go through"


@pytest.mark.asyncio
async def test_the_breaker_floor_protects_a_small_marked_set():
    """10% of a 3-edition set is 0, which would refuse every single clear on a
    fresh install. The absolute floor is what keeps the guard from being
    nonsense at small N."""
    assert int(3 * CLEAR_BREAKER_FRACTION) == 0
    resolve, marked = _poll([], _marked("/books/OL1M", "/books/OL2M", "/books/OL3M"))
    with resolve, marked:
        updates = await build_poll_updates([], _NOW)
    _, clear = _sets(updates)
    assert len(clear) == 3
    assert CLEAR_BREAKER_FLOOR >= 3


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
    marked = {f"/books/OL{i}M": {"key": f"/books/OL{i}M", "ia": [f"book{i}"], "_root_": f"/works/OL{i}W"} for i in range(500)}
    resolved = {"bookaaa": {"key": "/books/OL9001M", "root": "/works/OL9001W"}}
    with (
        patch("scripts.solr_updater.loan_availability_updater.resolve_edition_keys", AsyncMock(return_value=resolved)),
        patch("scripts.solr_updater.loan_availability_updater.fetch_marked_editions", AsyncMock(return_value=marked)),
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
    doc = {"key": "/books/OL1M", "ia": ["bookaaa"], "_root_": "/works/OL1W"}
    if marked_at is not None:
        doc["ebook_unavailable_at"] = marked_at
    return {"/books/OL1M": doc}


async def _poll_against(index_says: list[str], marked: dict, index_current_as_of: int) -> tuple[set, set]:
    resolved = {"bookaaa": _EDITION} if "bookaaa" in index_says else {}
    with (
        patch("scripts.solr_updater.loan_availability_updater.resolve_edition_keys", AsyncMock(return_value=resolved)),
        patch("scripts.solr_updater.loan_availability_updater.fetch_marked_editions", AsyncMock(return_value=marked)),
    ):
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
    mark, clear = await _poll_against([], _marked_doc(marked_at), index_current_as_of)
    assert clear == {"/books/OL1M"}, f"a mark {age_hours}h older than the index's currency must be cleared"


@pytest.mark.asyncio
async def test_a_mark_with_no_timestamp_is_clearable():
    """A doc that predates this daemon, or survived a reindex, carries no stamp.
    The index is the better authority on those, so they clear normally."""
    _, clear = await _poll_against([], _marked_doc(None), _MARKED_RECENTLY)
    assert clear == {"/books/OL1M"}


@pytest.mark.asyncio
async def test_a_poll_mark_carries_a_timestamp_so_the_next_poll_cannot_clear_it():
    """Marks from the POLL need the stamp as much as marks from the feed --
    without it the next poll reads epoch 0 and is free to clear immediately."""
    mark, _ = await _poll_against(["bookaaa"], {}, _MARKED_RECENTLY)
    assert mark == {"/books/OL1M"}
    with (
        patch("scripts.solr_updater.loan_availability_updater.resolve_edition_keys", AsyncMock(return_value={"bookaaa": _EDITION})),
        patch("scripts.solr_updater.loan_availability_updater.fetch_marked_editions", AsyncMock(return_value={})),
    ):
        updates = await build_poll_updates(["bookaaa"], _MARKED_RECENTLY)
    assert updates[0]["ebook_unavailable_at"]["set"] > 0, "a mark without a timestamp is clearable by the next poll"


def test_a_feed_mark_is_stamped_with_the_event_time_not_the_read_time():
    """A batch read at 10:00 can carry an event from 09:58. Stamping it 10:00
    would claim two minutes of protection the mark has not earned."""
    rows = [{"identifier": "bookaaa", "uid": 5, "event_type": "borrow", "extra": "{}", "time": "2001-09-09 01:46:40"}]
    dirty = collect_dirty_identifiers(rows)
    updates = build_solr_updates(dirty, {"bookaaa": _EDITION})
    assert updates[0]["ebook_unavailable_at"]["set"] == _MARKED_RECENTLY


def test_a_feed_mark_with_an_unreadable_time_falls_back_to_now():
    """Over-protect by seconds rather than under-protect: an unparsable row must
    not produce a mark stamped epoch 0, which the next poll would clear."""
    rows = [{"identifier": "bookaaa", "uid": 5, "event_type": "borrow", "extra": "{}", "time": "not-a-date"}]
    updates = build_solr_updates(collect_dirty_identifiers(rows), {"bookaaa": _EDITION})
    assert updates[0]["ebook_unavailable_at"]["set"] > _MARKED_RECENTLY


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
    marked = {"/books/OL1M": {"key": "/books/OL1M", "ia": ["bookaaa"], "_root_": "/works/OL1W", "ebook_unavailable_at": int(time.time()) - 1000}}
    solr = MagicMock(spec=Solr)
    solr.update_in_place_async.return_value = _OK_RESPONSE
    written: list[dict] = []

    async def capture(request, commit=False):
        written.extend(request)

    with (
        patch("scripts.solr_updater.loan_availability_updater.get_solr", return_value=solr),
        patch("scripts.solr_updater.loan_availability_updater.resolve_edition_keys", AsyncMock(return_value={})),
        patch("scripts.solr_updater.loan_availability_updater.fetch_marked_editions", AsyncMock(return_value=marked)),
        patch("scripts.solr_updater.loan_availability_updater.solr_update_in_place", AsyncMock(side_effect=capture)),
        patch("openlibrary.core.lending.get_checked_out_candidates_async", AsyncMock(return_value=[])),
        patch("scripts.solr_updater.loan_availability_updater.asyncio.sleep", AsyncMock(side_effect=SystemExit)),
        pytest.raises(SystemExit),
    ):
        await _poll_loop(poll_interval=0, es_lag_margin=margin, dry_run=False)

    cleared = [u for u in written if u.get("ebook_unavailable") == {"set": EBOOK_AVAILABLE}]
    assert bool(cleared) is expect_cleared, f"margin={margin} should {'clear' if expect_cleared else 'hold'} a mark 1000s old"
