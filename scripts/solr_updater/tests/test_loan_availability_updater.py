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
    # A flat ia:(...) query would also match the parent work's aggregate ia field.
    assert "type:edition" in call_args
    assert '"bookabc"' in call_args
    assert '"bookxyz"' in call_args


@pytest.mark.asyncio
async def test_resolve_edition_keys_escapes_quotes():
    """A malformed Lucene query would fail every poll."""
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
    """update_in_place_async returns a 400 body without raising."""
    with patch("scripts.solr_updater.loan_availability_updater.get_solr", return_value=MagicMock(spec=Solr)) as mock_get_solr:
        mock_get_solr.return_value.update_in_place_async.return_value = {
            "responseHeader": {"status": 400},
            "error": {"msg": "Can not satisfy 'update.partial.requireInPlace'"},
        }
        with pytest.raises(RuntimeError, match="Solr rejected the in-place update"):
            await solr_update_in_place([{"key": "/books/OL1M"}])


@pytest.mark.asyncio
async def test_a_large_write_is_split_into_batches():
    """In-place updates cost per document, so a full mark-everything write must not be one request."""
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
    """A write stopping after the marks only hides books; stopping after the clears publishes checked-out ones."""
    marks = [{"key": f"/books/OL{i}M", "_root_": "/works/OL1W", "ebook_unavailable": {"set": EBOOK_UNAVAILABLE}} for i in range(120)]
    clears = [{"key": f"/books/OL{i}M", "_root_": "/works/OL1W", "ebook_unavailable": {"set": EBOOK_AVAILABLE}} for i in range(120, 140)]
    solr = MagicMock(spec=Solr)
    solr.update_in_place_async = AsyncMock(return_value={"responseHeader": {"status": 0}})
    with patch("scripts.solr_updater.loan_availability_updater.get_solr", return_value=solr):
        await solr_update_in_place(marks + clears)
    written = [doc for call in solr.update_in_place_async.call_args_list for doc in call.args[0]]
    assert len(written) == 140, "every update written exactly once"
    positions = [i for i, d in enumerate(written) if d["ebook_unavailable"] == {"set": EBOOK_AVAILABLE}]
    # Every mark before every clear, not merely a mark first.
    assert positions == list(range(140 - 20, 140)), f"all 20 clears must come last, found them at {positions[:5]}..."


@pytest.mark.asyncio
async def test_a_failure_says_how_many_batches_had_already_landed(caplog):
    """ "Nothing was written" and "most of it was written" call for different responses."""
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
    """Solr's 400 names no document, so the log must carry sample keys."""
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
    # The marked-set read.
    return _EMPTY_RESULT


# ---------------------------------------------------------------------------
# resolve_edition_keys chunking
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_edition_keys_chunks_its_query():
    """One clause per identifier must stay under Solr's maxBooleanClauses."""
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
# build_poll_updates: the index's unavailable set reconciled against Solr's
# marks. resolve_edition_keys and fetch_solr_unavailable are patched out.
# ---------------------------------------------------------------------------

POLL_EDITIONS = {
    "bookaaa": {"key": "/books/OL1M", "root": "/works/OL1W", "ocaid": "bookaaa"},
    "bookbbb": {"key": "/books/OL2M", "root": "/works/OL2W", "ocaid": "bookbbb"},
    "bookccc": {"key": "/books/OL3M", "root": "/works/OL3W", "ocaid": "bookccc"},
}

# 2026-10-07T20:00:00Z
EVENT_EPOCH = 1791403200


def _index(*identifiers: str, at: int | None = EVENT_EPOCH) -> dict[str, int | None]:
    """An index read: identifier -> loan-event epoch. Dated by default, since an
    undated read gives the clear gate no horizon and nothing would clear."""
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
    """The index reflects expiry, so dropping out of its set means returned or expired."""
    resolve, marked = _poll(["bookaaa"], _marked("/books/OL1M", "/books/OL2M"))
    with resolve, marked:
        updates = await build_poll_updates(_index("bookaaa"))
    mark, clear = _sets(updates)
    assert clear == {"/books/OL2M"}
    assert mark == set()


@pytest.mark.asyncio
async def test_a_wiped_field_is_re_marked_by_the_next_poll():
    """A reindex drops `ebook_unavailable`; the next poll re-marks the whole unavailable set."""
    resolve, marked = _poll(list(POLL_EDITIONS), {})
    with resolve, marked:
        updates = await build_poll_updates(_index(*POLL_EDITIONS))
    mark, clear = _sets(updates)
    assert mark == {"/books/OL1M", "/books/OL2M", "/books/OL3M"}
    assert clear == set(), "an empty marked set has nothing to clear -- and must not invent any"


@pytest.mark.asyncio
async def test_an_unchanged_poll_writes_nothing():
    """Write volume tracks lending churn, not the poll rate."""
    resolve, marked = _poll(["bookaaa", "bookbbb"], _marked("/books/OL1M", "/books/OL2M"))
    with resolve, marked:
        updates = await build_poll_updates(_index("bookaaa", "bookbbb"))
    assert updates == []


def _many_marked(n: int) -> dict[str, dict]:
    return {f"/books/OL{i}M": {"key": f"/books/OL{i}M", "ia": [f"book{i}"], "_root_": f"/works/OL{i}W"} for i in range(n)}


@pytest.mark.asyncio
async def test_a_truncated_marked_read_is_refused_rather_than_treated_as_the_set():
    """An edition beyond the cap would read as returned, and be cleared."""
    mock_solr = MagicMock(spec=Solr)
    mock_solr.select_async.return_value = MagicMock(docs=[{"key": f"/books/OL{i}M", "ia": [], "_root_": "/works/OL1W"} for i in range(SOLR_UNAVAILABLE_MAX)])
    with patch("scripts.solr_updater.loan_availability_updater.get_solr", return_value=mock_solr), pytest.raises(PollRefused) as excinfo:
        await fetch_solr_unavailable()
    assert "cap" in str(excinfo.value)


# ---------------------------------------------------------------------------
# The clear gate: absence means "returned" only for marks older than the index.
# ---------------------------------------------------------------------------


def _marked_at(key: str, ocaid: str, stamp: int | None) -> dict:
    doc: dict = {"key": key, "ia": [ocaid], "_root_": key.replace("books", "works").replace("M", "W")}
    if stamp is not None:
        doc["ebook_unavailable_ts"] = stamp
    return doc


@pytest.mark.asyncio
async def test_a_mark_newer_than_the_index_is_held_not_cleared():
    """A mark newer than the index's newest event is absent because the index
    lags, not because the book came back; clearing it publishes a checked-out book."""
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
    """A gate that holds everything would otherwise pass the test above."""
    marked = {"/books/OL2M": _marked_at("/books/OL2M", "bookbbb", EVENT_EPOCH - 60)}
    with (
        patch("scripts.solr_updater.loan_availability_updater.resolve_edition_keys", AsyncMock(return_value={"bookaaa": POLL_EDITIONS["bookaaa"]})),
        patch("scripts.solr_updater.loan_availability_updater.fetch_solr_unavailable", AsyncMock(return_value=marked)),
    ):
        updates = await build_poll_updates({"bookaaa": EVENT_EPOCH})
    _, clear = _sets(updates)
    assert clear == {"/books/OL2M"}, "a mark the index is current enough to contradict must clear"


def test_a_mark_exactly_at_the_index_currency_is_held():
    """Strict `<`: a mark at the index's own instant is ambiguous, and ambiguity holds."""
    doc = _marked_at("/books/OL2M", "bookbbb", EVENT_EPOCH)
    clearable, held = older_than_es([doc], EVENT_EPOCH)
    assert clearable == []
    assert held == [doc]


def test_no_index_horizon_clears_nothing():
    """An undated or empty read is no information, never "everything was returned"."""
    doc = _marked_at("/books/OL2M", "bookbbb", 1)
    clearable, held = older_than_es([doc], None)
    assert clearable == []
    assert held == [doc]


def test_a_mark_with_no_stamp_is_treated_as_very_old_and_clears():
    """A stampless mark can only predate the stamp field, so it is old; holding it forever is worse."""
    doc = _marked_at("/books/OL2M", "bookbbb", None)
    clearable, held = older_than_es([doc], EVENT_EPOCH)
    assert clearable == [doc]
    assert held == []


# ---------------------------------------------------------------------------
# The timestamp: when the loan started, not when the daemon noticed.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_mark_is_stamped_with_the_loan_event_not_the_clock():
    """Stamping the poll time would make every mark look fresh to the clear gate."""
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
    """Unavailability dates from the latest loan event; an earlier one would make the mark clearable early."""
    doc = {"identifier": "bookaaa"}
    if borrow is not None:
        doc["lending___last_borrow"] = datetime.datetime.fromtimestamp(borrow, datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    if browse is not None:
        doc["lending___last_browse"] = datetime.datetime.fromtimestamp(browse, datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert lending._index_event_epoch(doc) == expected


def test_a_multi_valued_event_field_does_not_crash_the_parse():
    """Index fields can be lists; the latest value wins."""
    doc = {
        "identifier": "bookaaa",
        "lending___last_browse": ["2026-10-07T19:00:00Z", "2026-10-07T20:00:00Z"],
    }
    assert lending._index_event_epoch(doc) == EVENT_EPOCH


def test_an_unparsable_event_time_is_skipped_rather_than_raised_on():
    """A malformed date counts as no timestamp."""
    assert lending._index_event_epoch({"identifier": "b", "lending___last_browse": "not-a-date"}) is None
    assert lending._index_event_epoch({"identifier": "b", "lending___last_browse": ["nope", "2026-10-07T20:00:00Z"]}) == EVENT_EPOCH


@pytest.mark.asyncio
async def test_a_book_with_no_event_time_is_stamped_with_the_newest_in_the_batch():
    """Many index records carry no loan-event time; they take the newest one in the read.
    Over-estimating hides a book briefly; under-estimating publishes a checked-out one."""
    resolve, marked = _poll(["bookaaa", "bookbbb"], {})
    with resolve, marked:
        # bookbbb is undated; bookaaa is the newest event in the read.
        updates = await build_poll_updates({"bookaaa": EVENT_EPOCH, "bookbbb": None})
    stamps = {u["key"]: u["ebook_unavailable_ts"]["set"] for u in updates}
    assert stamps["/books/OL1M"] == EVENT_EPOCH, "the dated book keeps its own event time"
    assert stamps["/books/OL2M"] == EVENT_EPOCH, "and the undated one takes the newest_es_event in the batch"


@pytest.mark.asyncio
async def test_the_fallback_is_the_NEWEST_in_the_batch_not_the_oldest():
    """The oldest would be in range too, and would make every undated book clearable."""
    resolve, marked = _poll(["bookaaa", "bookbbb", "bookccc"], {})
    oldest, newest_es_event = EVENT_EPOCH - 86_400, EVENT_EPOCH
    with resolve, marked:
        updates = await build_poll_updates({"bookaaa": oldest, "bookbbb": newest_es_event, "bookccc": None})
    undated = next(u for u in updates if u["key"] == "/books/OL3M")
    assert undated["ebook_unavailable_ts"]["set"] == newest_es_event, "the undated book must take the NEWEST event in the batch"
    assert undated["ebook_unavailable_ts"]["set"] != oldest, "the oldest would be in range too, and would clear it immediately"


@pytest.mark.asyncio
async def test_a_batch_with_no_event_times_at_all_falls_back_to_the_clock_and_says_so(caplog):
    """With no event time anywhere the clock is the only answer, and it is logged loudly."""
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
    # A list means "dated by default"; see _index.
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
    """A bare update() rebuilds the document from stored fields, losing unstored ones."""
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
    # spec=Solr makes any other write method raise, so reaching here is the check.


@pytest.mark.asyncio
@patch("scripts.solr_updater.loan_availability_updater.get_solr")
@patch("scripts.solr_updater.loan_availability_updater.init_sentry")
@patch("scripts.solr_updater.loan_availability_updater.lending")
@patch("scripts.solr_updater.loan_availability_updater.infogami")
@patch("scripts.solr_updater.loan_availability_updater.load_config")
async def test_main_never_hard_commits(mock_config, mock_infogami, mock_lending, mock_sentry, mock_get_solr):
    """A hard commit invalidates every cache on the live Solr; autoSoftCommit/autoCommit already cover it."""
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
    """The previous poll's marks are a better answer than a partial read."""
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
# Launcher, truncated reads and the stamp
# ---------------------------------------------------------------------------


def test_the_shipped_launcher_invocation_matches_mains_signature():
    """An unknown flag makes argparse exit before the first poll, every restart, while the container looks healthy."""
    script = (Path(__file__).parents[2] / "solr_updater" / ".." / ".." / "docker" / "ol-solr-updater-start.sh").resolve()
    text = script.read_text()
    assert "loan_availability_updater.py" in text, f"launcher not found at {script}"

    # Join backslash continuations.
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
    """A short `docs` list under HTTP 200 would read as a mass return."""
    mock_solr = MagicMock(spec=Solr)
    result = MagicMock(docs=[{"key": "/books/OL1M", "ia": ["bookaaa"], "_root_": "/works/OL1W"}], num_found=500, response_header={})
    mock_solr.select_async.return_value = result
    with patch("scripts.solr_updater.loan_availability_updater.get_solr", return_value=mock_solr), pytest.raises(PollRefused) as excinfo:
        await fetch_solr_unavailable()
    assert "500" in str(excinfo.value)


@pytest.mark.asyncio
async def test_a_partial_solr_read_is_refused_rather_than_cleared():
    """`partialResults` is the only signal that `timeAllowed` tripped."""
    mock_solr = MagicMock(spec=Solr)
    result = MagicMock(docs=[{"key": "/books/OL1M", "ia": ["bookaaa"], "_root_": "/works/OL1W"}], num_found=1, response_header={"partialResults": True})
    mock_solr.select_async.return_value = result
    with patch("scripts.solr_updater.loan_availability_updater.get_solr", return_value=mock_solr), pytest.raises(PollRefused) as excinfo:
        await fetch_solr_unavailable()
    assert "partialResults" in str(excinfo.value)


@pytest.mark.asyncio
async def test_a_mark_carries_the_timestamp_in_the_same_update():
    """Separate writes could leave a mark with another write's stamp."""
    resolve, marked = _poll(["bookaaa"], {})
    with resolve, marked:
        updates = await build_poll_updates(_index("bookaaa"))
    assert len(updates) == 1
    assert updates[0]["ebook_unavailable"] == {"set": EBOOK_UNAVAILABLE}
    # Exact equality: a looser bound passes a milliseconds or constant stamp, which freezes every clear.
    assert updates[0]["ebook_unavailable_ts"]["set"] == EVENT_EPOCH


@pytest.mark.asyncio
async def test_a_clear_does_not_touch_the_timestamp():
    """`requireInPlace` cannot null a field, so the stamp is only meaningful while marked."""
    resolve, marked = _poll(["bookaaa"], _marked("/books/OL2M"))
    with resolve, marked:
        updates = await build_poll_updates(_index("bookaaa"))
    clear = [u for u in updates if u["ebook_unavailable"] == {"set": EBOOK_AVAILABLE}]
    assert len(clear) == 1
    assert "ebook_unavailable_ts" not in clear[0]


@pytest.mark.asyncio
async def test_a_truncated_edition_resolve_is_refused_rather_than_cleared():
    """An unresolved identifier reads as returned, so a short resolve would clear checked-out books."""
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
    """`partialResults` is the only signal that `timeAllowed` tripped."""
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
    """Most identifiers have no edition; the guard compares matched to returned, not to requested."""
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
    """Editions can share an ocaid, so matches may exceed the identifiers requested."""
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
