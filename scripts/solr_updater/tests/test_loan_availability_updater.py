"""Tests for loan_availability_updater.py"""

import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from openlibrary.core import lending
from openlibrary.core.lending import AVAILABILITY_BATCH_SIZE
from openlibrary.utils.solr import Solr
from scripts.solr_updater.loan_availability_updater import (
    BATCH_SIZE,
    EBOOK_AVAILABLE,
    EBOOK_UNAVAILABLE,
    LOAN_EVENTS_PER_DAY,
    OVERLAP_EVENTS,
    RECHECK_INTERVAL,
    RECHECK_MAX_EDITIONS,
    SOLR_QUERY_CHUNK,
    build_recheck_updates,
    build_reconcile_updates,
    build_solr_updates,
    collect_dirty_identifiers,
    ia_until_to_epoch,
    is_releasing_event,
    main,
    query_solr_uid,
    read_state,
    resolve_edition_keys,
    solr_update_in_place,
    write_state,
)


def test_read_state_missing(tmp_path):
    assert read_state(tmp_path / "nonexistent.state") == 0


def test_read_state_corrupt(tmp_path):
    p = tmp_path / "state"
    p.write_text("not-a-number\n")
    assert read_state(p) == 0


def test_read_write_state_roundtrip(tmp_path):
    p = tmp_path / "state"
    write_state(p, 42000)
    assert read_state(p) == 42000


def test_ia_until_to_epoch_valid():
    expected = int(datetime.datetime(2026, 5, 1, 15, 42, 43, tzinfo=datetime.UTC).timestamp())
    assert ia_until_to_epoch("2026-05-01 15:42:43") == expected


def test_ia_until_to_epoch_none():
    assert ia_until_to_epoch(None) is None


def test_ia_until_to_epoch_invalid():
    assert ia_until_to_epoch("not-a-date") is None


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


def test_collect_dirty_single_borrow():
    result = collect_dirty_identifiers([BORROW_ROW])
    assert result == {"bookabc": {"uid": 100, "until": "2026-05-15 10:00:00", "event_type": "borrow"}}


def test_collect_dirty_latest_uid_wins():
    result = collect_dirty_identifiers([BORROW_ROW, RETURN_ROW])
    assert result["bookabc"]["uid"] == 200
    assert result["bookabc"]["until"] is None


def test_collect_dirty_latest_uid_wins_reverse_order():
    result = collect_dirty_identifiers([RETURN_ROW, BORROW_ROW])
    assert result["bookabc"]["uid"] == 200


def test_collect_dirty_multiple_identifiers():
    result = collect_dirty_identifiers([BORROW_ROW, BROWSE_ROW, RETURN_ROW, EXPIRE_ROW])
    assert set(result) == {"bookabc", "bookxyz"}
    assert result["bookabc"]["uid"] == 200
    assert result["bookxyz"]["uid"] == 300


def test_collect_dirty_keeps_the_event_type_for_the_writer():
    """It used to be discarded here. build_solr_updates needs it to tell an
    acquiring event from a releasing one, so collapsing rows must not lose it."""
    row = {"identifier": "bookabc", "uid": 7, "event_type": "some_future_event", "extra": "{}"}
    assert collect_dirty_identifiers([row]) == {"bookabc": {"uid": 7, "until": None, "event_type": "some_future_event"}}


@pytest.mark.parametrize(
    ("event_type", "releasing"),
    [
        ("return", True),
        ("expire", True),
        ("expire_browse", True),
        ("expire_borrow", True),
        ("cancel_hold", True),
        ("RETURN", True),
        ("borrow", False),
        ("browse", False),
        ("renew_borrow", False),
        ("", False),
        ("some_future_event", False),
    ],
)
def test_is_releasing_event(event_type, releasing):
    """`expire_browse` is the case that motivates substring matching: an
    exact-match set built from the two verbs we first thought of would read it
    as acquiring and mark a just-expired loan unavailable."""
    assert is_releasing_event(event_type) is releasing


def test_collect_dirty_row_with_no_event_type_still_counts():
    row = {"identifier": "bookabc", "uid": 7}
    assert "bookabc" in collect_dirty_identifiers([row])


def test_collect_dirty_bad_extra_json():
    result = collect_dirty_identifiers([dict(BORROW_ROW, extra="not-json")])
    assert result["bookabc"]["until"] is None


def test_collect_dirty_extra_json_not_an_object():
    """extra could be valid JSON that isn't a dict; .get() on it must not crash."""
    result = collect_dirty_identifiers([dict(BORROW_ROW, extra="[1, 2, 3]")])
    assert result["bookabc"]["until"] is None


def test_collect_dirty_skips_malformed_rows():
    """A row missing identifier, or carrying a non-int uid, must be skipped rather
    than crash the updater."""
    rows = [
        {"event_type": "borrow", "uid": 5},  # no identifier
        {"identifier": "x", "event_type": "borrow"},  # no uid
        {"identifier": "y", "uid": "not-int", "event_type": "borrow"},  # non-int uid
        BORROW_ROW,  # the one valid row
    ]
    assert list(collect_dirty_identifiers(rows)) == ["bookabc"]


# ---------------------------------------------------------------------------
# build_solr_updates — ground truth decides, not the event
# ---------------------------------------------------------------------------


def test_build_solr_updates_acquiring_event_marks_unavailable():
    dirty = collect_dirty_identifiers([BORROW_ROW])
    updates = build_solr_updates(dirty, ID_TO_EDITION)
    assert updates == [
        {
            "key": "/books/OL1M",
            "_root_": "/works/OL1W",
            "ebook_unavailable": {"set": EBOOK_UNAVAILABLE},
            "loan_uid": {"set": 100},
            "ebook_becomes_available": {"set": ia_until_to_epoch("2026-05-15 10:00:00")},
        }
    ]


def test_build_solr_updates_releasing_event_writes_nothing():
    """The load-bearing asymmetry. A return does NOT mean available -- if anyone
    is queued the freed copy goes to the head of the waitlist -- so this path
    declines to write and leaves the clear to the ground-truth re-check.

    Writing EBOOK_AVAILABLE here instead would publish a waitlisted book as
    borrowable, and nothing would correct it: build_recheck_updates only ever
    flips unavailable -> available."""
    dirty = collect_dirty_identifiers([RETURN_ROW])
    assert build_solr_updates(dirty, ID_TO_EDITION) == []


@pytest.mark.parametrize("event_type", ["return", "expire_browse", "expire_borrow", "cancel_hold"])
def test_build_solr_updates_every_releasing_shape_writes_nothing(event_type):
    row = {"identifier": "bookabc", "uid": 100, "event_type": event_type, "extra": "{}"}
    assert build_solr_updates(collect_dirty_identifiers([row]), ID_TO_EDITION) == []


@pytest.mark.asyncio
async def test_build_solr_updates_borrow_of_multi_copy_item_is_marked_then_healed():
    """The multi-copy case, and the cost this design accepts: a borrow of one of
    several copies marks the edition unavailable even though it is still
    borrowable. That is the SAFE direction and it is temporary -- the re-check
    frees it against ground truth within RECHECK_INTERVAL.

    Asserted together so the pair cannot drift: if the write ever stopped
    happening, or the re-check ever stopped freeing, one of these fails."""
    dirty = collect_dirty_identifiers([BORROW_ROW])
    updates = build_solr_updates(dirty, ID_TO_EDITION)
    assert updates[0]["ebook_unavailable"] == {"set": EBOOK_UNAVAILABLE}

    # ...and the re-check frees it, because ground truth still says borrowable.
    mock_solr = MagicMock(spec=Solr)
    mock_solr.select_async.return_value = MagicMock(docs=[{"key": "/books/OL1M", "ia": ["bookabc"], "_root_": "/works/OL1W"}])
    with (
        patch("scripts.solr_updater.loan_availability_updater.get_solr", return_value=mock_solr),
        patch("openlibrary.core.lending.get_availability_async", return_value={"bookabc": AVAILABLE}),
    ):
        healed = await build_recheck_updates()
    assert healed == [{"key": "/books/OL1M", "_root_": "/works/OL1W", "ebook_unavailable": {"set": EBOOK_AVAILABLE}}]


def test_build_solr_updates_browse_is_acquiring():
    """A browse takes capacity as surely as a borrow does."""
    dirty = collect_dirty_identifiers([BROWSE_ROW])
    updates = build_solr_updates(dirty, ID_TO_EDITION)
    assert updates[0]["ebook_unavailable"] == {"set": EBOOK_UNAVAILABLE}


def test_build_solr_updates_unknown_event_type_is_treated_as_acquiring(caplog):
    """An unpublished vocabulary means this will happen. Erring toward
    unavailable is recoverable by the re-check; erring the other way publishes a
    book as borrowable and nothing corrects it. The WARNING is how we find out
    the real verb."""
    row = {"identifier": "bookabc", "uid": 100, "event_type": "some_future_event", "extra": "{}"}
    with caplog.at_level("WARNING"):
        updates = build_solr_updates(collect_dirty_identifiers([row]), ID_TO_EDITION)
    assert updates[0]["ebook_unavailable"] == {"set": EBOOK_UNAVAILABLE}
    assert "some_future_event" in caplog.text


def test_build_solr_updates_does_not_consult_availability():
    """The decoupling, asserted rather than assumed: if the steady-state path
    regained a ground-truth call, a slow availability service would once again
    be able to stall feed ingestion."""
    dirty = collect_dirty_identifiers([BORROW_ROW])
    with patch("openlibrary.core.lending.get_availability_async", side_effect=AssertionError("must not be called")):
        assert build_solr_updates(dirty, ID_TO_EDITION)


def test_build_solr_updates_unknown_identifier_skipped():
    dirty = collect_dirty_identifiers([BORROW_ROW])
    assert build_solr_updates(dirty, {}) == []


def test_build_solr_updates_unavailable_without_until_omits_becomes_available():
    """No expiry in the event means no advisory timestamp; the re-check does not
    depend on this field."""
    row = {"identifier": "bookabc", "uid": 100, "event_type": "borrow", "extra": "{}"}
    updates = build_solr_updates(collect_dirty_identifiers([row]), ID_TO_EDITION)
    assert "ebook_becomes_available" not in updates[0]


def test_build_solr_updates_mixed_batch():
    """bookabc's latest event is a return (uid 200) so it writes nothing;
    bookxyz's latest is an expire (uid 300) so it writes nothing either. The
    collapse-to-latest is what decides, not the presence of a borrow earlier in
    the batch."""
    dirty = collect_dirty_identifiers([BORROW_ROW, BROWSE_ROW, RETURN_ROW, EXPIRE_ROW])
    assert build_solr_updates(dirty, ID_TO_EDITION) == []


def test_build_solr_updates_mixed_batch_writes_the_still_borrowed_one():
    dirty = collect_dirty_identifiers([RETURN_ROW, BROWSE_ROW])
    updates = build_solr_updates(dirty, ID_TO_EDITION)
    assert [u["key"] for u in updates] == ["/books/OL2M"]
    assert updates[0]["loan_uid"] == {"set": 150}


# ---------------------------------------------------------------------------
# Cold start: the one place that DOES depend on ground truth
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_reconcile_updates_marks_only_the_unavailable():
    with (
        patch(
            "scripts.solr_updater.loan_availability_updater.resolve_edition_keys",
            return_value=ID_TO_EDITION,
        ),
        patch(
            "openlibrary.core.lending.get_availability_async",
            return_value={"bookabc": UNAVAILABLE, "bookxyz": AVAILABLE},
        ),
    ):
        updates = await build_reconcile_updates(["bookabc", "bookxyz"])
    assert updates == [{"key": "/books/OL1M", "_root_": "/works/OL1W", "ebook_unavailable": {"set": EBOOK_UNAVAILABLE}}]


@pytest.mark.asyncio
async def test_build_reconcile_updates_empty_input_asks_nothing():
    with patch("openlibrary.core.lending.get_availability_async", side_effect=AssertionError("must not be called")):
        assert await build_reconcile_updates([]) == []


@pytest.mark.asyncio
async def test_build_reconcile_updates_raises_when_ground_truth_is_silent():
    """Cold start has no event to fall back on, so a silent availability service
    must abort the start rather than leave the index unmarked -- which would
    publish every on-loan book as borrowable."""
    with (
        patch(
            "scripts.solr_updater.loan_availability_updater.resolve_edition_keys",
            return_value=ID_TO_EDITION,
        ),
        patch("openlibrary.core.lending.get_availability_async", return_value={}),
        pytest.raises(RuntimeError, match="refusing to reconcile"),
    ):
        await build_reconcile_updates(["bookabc"])


# ---------------------------------------------------------------------------
# Solr plumbing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_query_solr_uid_with_data():
    mock_result = MagicMock()
    mock_result.docs = [{"loan_uid": 42000}]
    with patch("scripts.solr_updater.loan_availability_updater.get_solr", return_value=MagicMock(spec=Solr)) as mock_get_solr:
        mock_get_solr.return_value.select_async.return_value = mock_result
        assert await query_solr_uid() == 42000
    call_args = str(mock_get_solr.return_value.select_async.call_args)
    assert "loan_uid desc" in call_args


@pytest.mark.asyncio
async def test_query_solr_uid_empty():
    mock_result = MagicMock()
    mock_result.docs = []
    with patch("scripts.solr_updater.loan_availability_updater.get_solr", return_value=MagicMock(spec=Solr)) as mock_get_solr:
        mock_get_solr.return_value.select_async.return_value = mock_result
        assert await query_solr_uid() == 0


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


@pytest.mark.asyncio
async def test_build_recheck_updates_frees_only_available():
    with (
        patch("scripts.solr_updater.loan_availability_updater.get_solr", return_value=MagicMock(spec=Solr)) as mock_get_solr,
        patch("scripts.solr_updater.loan_availability_updater.lending") as mock_lending,
    ):
        mock_get_solr.return_value.select_async.return_value = _recheck_docs()
        mock_lending.get_availability_async = AsyncMock(return_value={"freed": AVAILABLE, "stillout": UNAVAILABLE})
        mock_lending.is_available_for_loan.side_effect = lambda a: bool(a.get("available_to_borrow"))
        updates = await build_recheck_updates()

    assert updates == [
        {
            "key": "/books/OL99M",
            "_root_": "/works/OL99W",
            "ebook_unavailable": {"set": EBOOK_AVAILABLE},
        }
    ]
    call_args = str(mock_get_solr.return_value.select_async.call_args)
    assert "type:edition" in call_args
    assert f"ebook_unavailable:{EBOOK_UNAVAILABLE}" in call_args


@pytest.mark.asyncio
async def test_build_recheck_updates_no_answer_leaves_edition_marked():
    """An edition the service says nothing about keeps its unavailable marker."""
    with (
        patch("scripts.solr_updater.loan_availability_updater.get_solr", return_value=MagicMock(spec=Solr)) as mock_get_solr,
        patch("scripts.solr_updater.loan_availability_updater.lending") as mock_lending,
    ):
        mock_get_solr.return_value.select_async.return_value = _recheck_docs()
        mock_lending.get_availability_async = AsyncMock(return_value={})
        assert await build_recheck_updates() == []


@pytest.mark.asyncio
async def test_build_recheck_updates_empty_index():
    empty = MagicMock()
    empty.docs = []
    with (
        patch("scripts.solr_updater.loan_availability_updater.get_solr", return_value=MagicMock(spec=Solr)) as mock_get_solr,
        patch("scripts.solr_updater.loan_availability_updater.lending") as mock_lending,
    ):
        mock_get_solr.return_value.select_async.return_value = empty
        assert await build_recheck_updates() == []
        mock_lending.get_availability_async.assert_not_called()


@pytest.mark.asyncio
async def test_build_recheck_updates_dedupes_multi_ocaid_edition():
    """One edition can carry several ocaids; it must be written at most once."""
    result = MagicMock()
    result.docs = [{"key": "/books/OL99M", "ia": ["a", "b"], "_root_": "/works/OL99W"}]
    with (
        patch("scripts.solr_updater.loan_availability_updater.get_solr", return_value=MagicMock(spec=Solr)) as mock_get_solr,
        patch("scripts.solr_updater.loan_availability_updater.lending") as mock_lending,
    ):
        mock_get_solr.return_value.select_async.return_value = result
        mock_lending.get_availability_async = AsyncMock(return_value={"a": AVAILABLE, "b": AVAILABLE})
        mock_lending.is_available_for_loan.return_value = True
        assert len(await build_recheck_updates()) == 1


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
    if "loan_uid" in query:
        return _EMPTY_RESULT
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


async def _run_main_one_iteration(tmp_path, solr_mock, lending_mock, first_batch_rows, availability=None):
    """Run main() through exactly one event-processing iteration."""
    state_file = tmp_path / "state"
    state_file.write_text("99")  # pre-seed so we skip startup init

    _wire_lending(lending_mock, first_batch_rows, availability)

    with pytest.raises(SystemExit):
        await main("fake_config.yml", state_file=str(state_file), poll_interval=0)

    return state_file


@pytest.mark.asyncio
@patch("scripts.solr_updater.loan_availability_updater.get_solr")
@patch("scripts.solr_updater.loan_availability_updater.init_sentry")
@patch("scripts.solr_updater.loan_availability_updater.lending")
@patch("scripts.solr_updater.loan_availability_updater.infogami")
@patch("scripts.solr_updater.loan_availability_updater.load_config")
async def test_main_calls_update_in_place_not_bare_update(mock_config, mock_infogami, mock_lending, mock_sentry, mock_get_solr, tmp_path):
    """The daemon must call update_in_place(), never bare update(), at all Solr write
    sites -- ebook_unavailable/ebook_becomes_available are numeric specifically so
    this is possible."""
    solr = MagicMock(spec=Solr)
    mock_get_solr.return_value = solr
    solr.select_async.side_effect = _select_side_effect
    solr.update_in_place_async.return_value = _OK_RESPONSE

    await _run_main_one_iteration(tmp_path, solr, mock_lending, [_BORROW_ROW])

    assert solr.update_in_place_async.called, "update_in_place_async() was never called"


@pytest.mark.asyncio
@patch("scripts.solr_updater.loan_availability_updater.get_solr")
@patch("scripts.solr_updater.loan_availability_updater.init_sentry")
@patch("scripts.solr_updater.loan_availability_updater.lending")
@patch("scripts.solr_updater.loan_availability_updater.infogami")
@patch("scripts.solr_updater.loan_availability_updater.load_config")
async def test_main_steady_state_never_calls_availability(mock_config, mock_infogami, mock_lending, mock_sentry, mock_get_solr, tmp_path):
    """Replaces a test that asserted WHICH ids were sent to the availability
    service. The steady-state path no longer sends any: it writes from the
    events, so a slow or failing availability service cannot stall ingestion.

    The re-check still uses it, so this pins recheck_interval high enough not to
    fire during the single iteration under test."""
    solr = MagicMock(spec=Solr)
    mock_get_solr.return_value = solr
    solr.select_async.side_effect = _select_side_effect
    solr.update_in_place_async.return_value = _OK_RESPONSE

    state_file = tmp_path / "state"
    state_file.write_text("99")
    _wire_lending(mock_lending, [_BORROW_ROW])

    with pytest.raises(SystemExit):
        await main("fake_config.yml", state_file=str(state_file), poll_interval=0, recheck_interval=10_000)

    mock_lending.get_availability_async.assert_not_called()
    assert solr.update_in_place_async.called


@pytest.mark.asyncio
@patch("scripts.solr_updater.loan_availability_updater.get_solr")
@patch("scripts.solr_updater.loan_availability_updater.init_sentry")
@patch("scripts.solr_updater.loan_availability_updater.lending")
@patch("scripts.solr_updater.loan_availability_updater.infogami")
@patch("scripts.solr_updater.loan_availability_updater.load_config")
async def test_main_availability_silence_no_longer_stalls_the_cursor(mock_config, mock_infogami, mock_lending, mock_sentry, mock_get_solr, tmp_path):
    """This assertion is INVERTED from the previous design, deliberately.

    It used to hold the cursor when the availability service answered nothing,
    so that those events could be retried. That coupled feed ingestion to a
    lagging dependency: while availability was down, nothing was consumed at
    all. The steady-state path no longer asks, so the cursor advances on the
    events alone and the re-check reconciles later."""
    solr = MagicMock(spec=Solr)
    mock_get_solr.return_value = solr
    solr.select_async.side_effect = _select_side_effect
    solr.update_in_place_async.return_value = _OK_RESPONSE

    state_file = await _run_main_one_iteration(tmp_path, solr, mock_lending, [_BORROW_ROW], availability={})

    assert state_file.read_text().strip() == "100", "cursor must advance without any availability answer"
    assert solr.update_in_place_async.called


@pytest.mark.asyncio
@patch("scripts.solr_updater.loan_availability_updater.get_solr")
@patch("scripts.solr_updater.loan_availability_updater.init_sentry")
@patch("scripts.solr_updater.loan_availability_updater.lending")
@patch("scripts.solr_updater.loan_availability_updater.infogami")
@patch("scripts.solr_updater.loan_availability_updater.load_config")
async def test_main_update_transport_failure_does_not_advance_state(mock_config, mock_infogami, mock_lending, mock_sentry, mock_get_solr, tmp_path):
    """If the Solr update_in_place call raises, the state file must NOT be advanced."""
    solr = MagicMock(spec=Solr)
    mock_get_solr.return_value = solr
    solr.select_async.side_effect = _select_side_effect
    solr.update_in_place_async.side_effect = RuntimeError("Solr unreachable")

    state_file = await _run_main_one_iteration(tmp_path, solr, mock_lending, [_BORROW_ROW])

    assert state_file.read_text().strip() == "99", "write_state was called even though the Solr update failed"


@pytest.mark.asyncio
@patch("scripts.solr_updater.loan_availability_updater.get_solr")
@patch("scripts.solr_updater.loan_availability_updater.init_sentry")
@patch("scripts.solr_updater.loan_availability_updater.lending")
@patch("scripts.solr_updater.loan_availability_updater.infogami")
@patch("scripts.solr_updater.loan_availability_updater.load_config")
async def test_main_update_nonzero_status_does_not_advance_state(mock_config, mock_infogami, mock_lending, mock_sentry, mock_get_solr, tmp_path):
    """Solr responds with a non-zero responseHeader.status (e.g. a rejected in-place
    update) without the HTTP layer raising. This must still be treated as a failure --
    state must NOT be advanced."""
    solr = MagicMock(spec=Solr)
    mock_get_solr.return_value = solr
    solr.select_async.side_effect = _select_side_effect
    solr.update_in_place_async.return_value = {"responseHeader": {"status": 400}, "error": {"msg": "rejected"}}

    state_file = await _run_main_one_iteration(tmp_path, solr, mock_lending, [_BORROW_ROW])

    assert state_file.read_text().strip() == "99", "write_state was called even though Solr reported a non-zero status"


@pytest.mark.asyncio
@patch("scripts.solr_updater.loan_availability_updater.get_solr")
@patch("scripts.solr_updater.loan_availability_updater.init_sentry")
@patch("scripts.solr_updater.loan_availability_updater.lending")
@patch("scripts.solr_updater.loan_availability_updater.infogami")
@patch("scripts.solr_updater.loan_availability_updater.load_config")
async def test_main_recheck_failure_is_non_fatal(mock_config, mock_infogami, mock_lending, mock_sentry, mock_get_solr, tmp_path):
    """Re-check failure must not prevent state advancement: the main updates already
    committed, and the re-check retries automatically next pass."""
    solr = MagicMock(spec=Solr)
    mock_get_solr.return_value = solr

    def select_side_effect_with_recheck(*args, **kwargs):
        query = kwargs.get("query", "") or (args[0] if args else "")
        if "loan_uid" in query:
            return _EMPTY_RESULT
        if "ia:" in query:
            return _RESOLVE_RESULT
        return _RECHECK_RESULT

    solr.select_async.side_effect = select_side_effect_with_recheck

    update_call_count = [0]

    def update_in_place_side_effect(docs, commit=False):
        update_call_count[0] += 1
        if update_call_count[0] == 2:
            # Second call is the re-check update — make it fail
            raise RuntimeError("transient Solr error")
        return _OK_RESPONSE

    solr.update_in_place_async.side_effect = update_in_place_side_effect

    state_file = tmp_path / "state"
    state_file.write_text("99")
    _wire_lending(mock_lending, [_BORROW_ROW], availability={"bookabc": AVAILABLE, "stale": AVAILABLE})

    with pytest.raises(SystemExit):
        await main("fake_config.yml", state_file=str(state_file), poll_interval=0, recheck_interval=0)

    assert state_file.read_text().strip() == "100", "write_state was NOT called even though only the re-check (non-fatal) failed"


@pytest.mark.asyncio
@patch("scripts.solr_updater.loan_availability_updater.get_solr")
@patch("scripts.solr_updater.loan_availability_updater.query_solr_uid")
@patch("scripts.solr_updater.loan_availability_updater.init_sentry")
@patch("scripts.solr_updater.loan_availability_updater.lending")
@patch("scripts.solr_updater.loan_availability_updater.infogami")
@patch("scripts.solr_updater.loan_availability_updater.load_config")
async def test_main_reset_seeds_from_the_index_not_from_solrs_cursor(
    mock_config, mock_infogami, mock_lending, mock_sentry, mock_query_uid, mock_get_solr, tmp_path
):
    """--reset must rebuild, never resume from a stale loan_uid still in Solr.

    The mechanism changed: this used to assert a backwards search for a
    14-day-old uid. The seed is now a single index query, so what must hold is
    that --reset goes to the index and places its cursor from the feed head,
    and that a stale Solr cursor cannot short-circuit it."""
    mock_query_uid.return_value = 200001  # stale high uid lingering in Solr
    solr = MagicMock(spec=Solr)
    mock_get_solr.return_value = solr
    solr.select_async.side_effect = _select_side_effect
    mock_lending.get_checked_out_candidates_async = AsyncMock(return_value=[])
    mock_lending.get_loan_changes = AsyncMock(
        side_effect=[
            {"status": "OK", "rows": [], "latest_uid": 42},  # head probe
            {"status": "OK", "rows": [], "latest_uid": 42},  # overlap replay: nothing
            SystemExit(0),
        ]
    )

    state_file = tmp_path / "state"
    with pytest.raises(SystemExit):
        await main("fake_config.yml", state_file=str(state_file), poll_interval=0, reset=True)

    mock_lending.get_checked_out_candidates_async.assert_awaited_once()
    mock_query_uid.assert_not_called()
    assert state_file.read_text().strip() == "42", "cursor should come from the feed head, not Solr"


@pytest.mark.asyncio
@patch("scripts.solr_updater.loan_availability_updater.get_solr")
@patch("scripts.solr_updater.loan_availability_updater.init_sentry")
@patch("scripts.solr_updater.loan_availability_updater.lending")
@patch("scripts.solr_updater.loan_availability_updater.infogami")
@patch("scripts.solr_updater.loan_availability_updater.load_config")
async def test_main_survives_malformed_row(mock_config, mock_infogami, mock_lending, mock_sentry, mock_get_solr, tmp_path):
    """A batch containing a malformed row must not crash main; the cursor advances
    using the valid rows' uids."""
    solr = MagicMock(spec=Solr)
    mock_get_solr.return_value = solr
    solr.select_async.side_effect = _select_side_effect
    solr.update_in_place_async.return_value = _OK_RESPONSE
    malformed = {"identifier": "broken", "event_type": "borrow"}  # missing uid
    state_file = await _run_main_one_iteration(tmp_path, solr, mock_lending, [malformed, _RETURN_ROW])
    assert state_file.read_text().strip() == "100"  # advanced past the batch via the valid uid; no crash


# ---------------------------------------------------------------------------
# Cold start inside main()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("scripts.solr_updater.loan_availability_updater.get_solr")
@patch("scripts.solr_updater.loan_availability_updater.query_solr_uid", return_value=0)
@patch("scripts.solr_updater.loan_availability_updater.init_sentry")
@patch("scripts.solr_updater.loan_availability_updater.lending")
@patch("scripts.solr_updater.loan_availability_updater.infogami")
@patch("scripts.solr_updater.loan_availability_updater.load_config")
async def test_main_cold_start_reconciles_before_following_events(mock_config, mock_infogami, mock_lending, mock_sentry, mock_uid, mock_get_solr, tmp_path):
    """The seed is the index, and ground truth still decides every mark.

    The index is a lagged view, so its identifiers are candidates only: they go
    through the availability service before anything is written. What this pins
    is the order -- seeded, settled and committed BEFORE the event path runs --
    and that the index set is never written as-is.
    """
    solr = MagicMock(spec=Solr)
    mock_get_solr.return_value = solr
    solr.select_async.side_effect = _select_side_effect
    solr.update_in_place_async.return_value = _OK_RESPONSE

    mock_lending.get_checked_out_candidates_async = AsyncMock(return_value=["bookabc"])
    mock_lending.get_loan_changes = AsyncMock(
        side_effect=[
            {"status": "OK", "rows": [], "latest_uid": 100},  # head probe
            {"status": "OK", "rows": [], "latest_uid": 100},  # overlap: nothing new
            SystemExit(0),
        ]
    )
    mock_lending.get_availability_async = AsyncMock(return_value={"bookabc": UNAVAILABLE})
    mock_lending.is_available_for_loan.side_effect = lambda a: bool(a.get("available_to_browse") or a.get("available_to_borrow"))

    state_file = tmp_path / "state"
    with pytest.raises(SystemExit):
        await main("fake_config.yml", state_file=str(state_file), poll_interval=0, recheck_interval=10_000)

    mock_lending.get_checked_out_candidates_async.assert_awaited_once()
    # Ground truth was consulted about the index's candidate...
    assert mock_lending.get_availability_async.called
    # ...and the mark was committed before any event was followed.
    first_write = solr.update_in_place_async.call_args_list[0]
    assert first_write.args[0] == [{"key": "/books/OL1M", "_root_": "/works/OL1W", "ebook_unavailable": {"set": EBOOK_UNAVAILABLE}}]
    assert first_write.kwargs.get("commit") is True
    assert state_file.read_text().strip() == "100", "cursor should sit at the feed head after the overlap"


@pytest.mark.asyncio
@patch("scripts.solr_updater.loan_availability_updater.get_solr")
@patch("scripts.solr_updater.loan_availability_updater.query_solr_uid", return_value=0)
@patch("scripts.solr_updater.loan_availability_updater.init_sentry")
@patch("scripts.solr_updater.loan_availability_updater.lending")
@patch("scripts.solr_updater.loan_availability_updater.infogami")
@patch("scripts.solr_updater.loan_availability_updater.load_config")
async def test_main_cold_start_refuses_to_start_without_ground_truth(mock_config, mock_infogami, mock_lending, mock_sentry, mock_uid, mock_get_solr, tmp_path):
    """The one place a ground-truth outage SHOULD stop us.

    Steady state deliberately carries on without the availability service. Cold
    start cannot: there is no prior state to fall back on, so beginning from the
    head with an unmarked index would publish every on-loan book as borrowable.
    Failing loudly is the safe outcome here, and it is the opposite of the
    steady-state rule on purpose."""
    solr = MagicMock(spec=Solr)
    mock_get_solr.return_value = solr
    solr.select_async.side_effect = _select_side_effect

    mock_lending.get_checked_out_candidates_async = AsyncMock(return_value=["bookabc"])
    mock_lending.get_loan_changes = AsyncMock(
        side_effect=[
            {"status": "OK", "rows": [], "latest_uid": 100},
            {"status": "OK", "rows": [], "latest_uid": 100},
            # Terminator. Without it, a regression that skipped the cold start
            # would drop into the steady-state loop, exhaust this mock, and have
            # the StopIteration swallowed by the retry handler's `except
            # Exception` -- so the test would HANG rather than fail. A hang reads
            # as an infrastructure problem, not as a caught regression.
            SystemExit(0),
        ]
    )
    mock_lending.get_availability_async = AsyncMock(return_value={})

    state_file = tmp_path / "state"
    with pytest.raises(RuntimeError, match="refusing to reconcile"):
        await main("fake_config.yml", state_file=str(state_file), poll_interval=0)

    solr.update_in_place_async.assert_not_called()
    assert not state_file.exists(), "state must not be written when the cold start aborted"


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


@pytest.mark.asyncio
async def test_reconcile_refuses_on_partial_availability_coverage():
    """The guard used to fire only on TOTAL silence. `get_availability_async`
    swallows a failed chunk and continues, so a widespread timeout still
    returns a non-empty dict -- and most genuinely-on-loan books would be left
    unmarked, which the re-check cannot correct because it only inspects books
    already marked."""
    ids = [f"ocaid_{i}" for i in range(10)]
    editions = {i: {"key": f"/books/OL{n}M", "root": f"/works/OL{n}W"} for n, i in enumerate(ids)}
    with (
        patch("scripts.solr_updater.loan_availability_updater.resolve_edition_keys", return_value=editions),
        patch("openlibrary.core.lending.get_availability_async", return_value={ids[0]: UNAVAILABLE}),
        pytest.raises(RuntimeError, match="refusing to reconcile"),
    ):
        await build_reconcile_updates(ids)


@pytest.mark.asyncio
async def test_reconcile_accepts_full_coverage():
    ids = [f"ocaid_{i}" for i in range(10)]
    editions = {i: {"key": f"/books/OL{n}M", "root": f"/works/OL{n}W"} for n, i in enumerate(ids)}
    with (
        patch("scripts.solr_updater.loan_availability_updater.resolve_edition_keys", return_value=editions),
        patch("openlibrary.core.lending.get_availability_async", return_value=dict.fromkeys(ids, UNAVAILABLE)),
    ):
        assert len(await build_reconcile_updates(ids)) == 10


@pytest.mark.asyncio
async def test_recheck_sorts_so_the_window_rotates():
    """Unsorted, the select returns the same lowest-docid prefix every pass, so
    once more than RECHECK_MAX_EDITIONS are marked the tail is re-checked only
    as fast as the head frees -- measured at ~5 editions per pass, stranding an
    over-marked book for months."""
    mock_solr = MagicMock(spec=Solr)
    mock_solr.select_async.return_value = MagicMock(docs=[])
    with patch("scripts.solr_updater.loan_availability_updater.get_solr", return_value=mock_solr):
        await build_recheck_updates()
    kwargs = mock_solr.select_async.call_args.kwargs
    assert kwargs.get("sort") == "loan_uid asc"
    assert "loan_uid" in kwargs["fields"], "loan_uid must be selected for the clear guard"


@pytest.mark.asyncio
async def test_recheck_will_not_clear_an_edition_the_follower_just_marked():
    """The unrecoverable direction. `get_availability_async` is ~100 sequential
    requests taking tens of seconds; the follower keeps consuming events
    throughout. A book borrowed during that window is marked by the follower
    and would then be cleared by a snapshot predating the borrow -- published
    as borrowable while on loan, with the event already behind the cursor and
    the re-check unable to re-mark it."""
    mock_solr = MagicMock(spec=Solr)
    mock_solr.select_async.return_value = MagicMock(docs=[{"key": "/books/OL1M", "ia": ["bookabc"], "_root_": "/works/OL1W", "loan_uid": 5}])
    with (
        patch("scripts.solr_updater.loan_availability_updater.get_solr", return_value=mock_solr),
        patch("openlibrary.core.lending.get_availability_async", return_value={"bookabc": AVAILABLE}),
    ):
        assert await build_recheck_updates(marked_during_pass={"/books/OL1M"}) == []
        assert await build_recheck_updates(marked_during_pass=set()) != []


@pytest.mark.asyncio
@patch("scripts.solr_updater.loan_availability_updater.get_solr")
@patch("scripts.solr_updater.loan_availability_updater.init_sentry")
@patch("scripts.solr_updater.loan_availability_updater.lending")
@patch("scripts.solr_updater.loan_availability_updater.infogami")
@patch("scripts.solr_updater.loan_availability_updater.load_config")
async def test_main_does_not_spin_when_the_feed_returns_nothing_newer(mock_config, mock_infogami, mock_lending, mock_sentry, mock_get_solr, tmp_path):
    """A full page whose uids never pass the cursor spun the loop with no sleep
    -- 201 API calls in 0.21s, hammering IA and Solr -- and `last_uid = new_uid`
    was unconditional, so the cursor could also move backwards."""
    solr = MagicMock(spec=Solr)
    mock_get_solr.return_value = solr
    solr.select_async.side_effect = _select_side_effect
    solr.update_in_place_async.return_value = _OK_RESPONSE

    stale = {"identifier": "bookabc", "uid": 5, "event_type": "borrow", "extra": "{}"}
    mock_lending.get_loan_changes = AsyncMock(
        side_effect=[
            {"status": "OK", "rows": [stale], "latest_uid": 5},
            SystemExit(0),
        ]
    )
    state_file = tmp_path / "state"
    state_file.write_text("99")

    with pytest.raises(SystemExit):
        await main("fake_config.yml", state_file=str(state_file), poll_interval=0, recheck_interval=10_000)

    assert state_file.read_text().strip() == "99", "cursor moved backwards"
    solr.update_in_place_async.assert_not_called()


@pytest.mark.asyncio
@patch("scripts.solr_updater.loan_availability_updater.get_solr")
@patch("scripts.solr_updater.loan_availability_updater.init_sentry")
@patch("scripts.solr_updater.loan_availability_updater.lending")
@patch("scripts.solr_updater.loan_availability_updater.infogami")
@patch("scripts.solr_updater.loan_availability_updater.load_config")
async def test_main_does_not_hard_commit_every_cycle(mock_config, mock_infogami, mock_lending, mock_sentry, mock_get_solr, tmp_path):
    """A hard commit opens a new searcher and invalidates every Solr cache. Done
    per cycle on the Solr serving openlibrary.org, with no pacing during
    catch-up, that is a real cost -- and it bought nothing: last_uid advances in
    memory before any commit, and autoCommit persists the docs regardless."""
    solr = MagicMock(spec=Solr)
    mock_get_solr.return_value = solr
    solr.select_async.side_effect = _select_side_effect
    solr.update_in_place_async.return_value = _OK_RESPONSE

    await _run_main_one_iteration(tmp_path, solr, mock_lending, [_BORROW_ROW])

    commits = [c for c in solr.update_in_place_async.call_args_list if c.kwargs.get("commit")]
    assert commits == [], f"expected no hard commit, got {len(commits)}"


@pytest.mark.asyncio
@patch("scripts.solr_updater.loan_availability_updater.get_solr")
@patch("scripts.solr_updater.loan_availability_updater.init_sentry")
@patch("scripts.solr_updater.loan_availability_updater.lending")
@patch("scripts.solr_updater.loan_availability_updater.infogami")
@patch("scripts.solr_updater.loan_availability_updater.load_config")
async def test_main_clamps_a_cursor_that_is_ahead_of_the_feed(mock_config, mock_infogami, mock_lending, mock_sentry, mock_get_solr, tmp_path):
    """Observed in a live run: a cursor ahead of the feed head returns zero rows
    forever and logs nothing above DEBUG, so the daemon looks healthy while
    doing nothing. `latest_uid` is on every response and was only read at
    startup."""
    solr = MagicMock(spec=Solr)
    mock_get_solr.return_value = solr
    solr.select_async.side_effect = _select_side_effect

    mock_lending.get_loan_changes = AsyncMock(
        side_effect=[
            {"status": "OK", "rows": [], "latest_uid": 50},
            SystemExit(0),
        ]
    )
    state_file = tmp_path / "state"
    state_file.write_text("200001")

    with pytest.raises(SystemExit):
        await main("fake_config.yml", state_file=str(state_file), poll_interval=0, recheck_interval=10_000)

    assert state_file.read_text().strip() == "50", "cursor was not clamped to the feed head"


def test_a_recheck_pass_fits_inside_its_own_interval():
    """Sizing, asserted rather than left to a comment.

    The re-check sends AVAILABILITY_BATCH_SIZE ids per sequential request. If a
    pass can outlast RECHECK_INTERVAL -- which it could at the original cap of
    10000, once archive.org starts timing out -- the re-check runs back to back
    forever and, sharing a single-threaded loop with the follower, stops the
    feed being consumed for the length of the outage."""
    requests_per_pass = RECHECK_MAX_EDITIONS / AVAILABILITY_BATCH_SIZE
    worst_case_seconds = requests_per_pass * 10  # a timing-out request
    assert worst_case_seconds < RECHECK_INTERVAL, (
        f"{requests_per_pass:.0f} sequential requests could take {worst_case_seconds:.0f}s, "
        f"which outlasts the {RECHECK_INTERVAL}s interval and would starve the follower"
    )


@pytest.mark.asyncio
async def test_recheck_says_so_when_ground_truth_is_unreachable():
    """An archive.org outage must be visible, not silent -- and must free nothing."""
    mock_solr = MagicMock(spec=Solr)
    mock_solr.select_async.return_value = MagicMock(docs=[{"key": "/books/OL1M", "ia": ["bookabc"], "_root_": "/works/OL1W", "loan_uid": 5}])
    with (
        patch("scripts.solr_updater.loan_availability_updater.get_solr", return_value=mock_solr),
        patch("openlibrary.core.lending.get_availability_async", return_value={}),
    ):
        assert await build_recheck_updates() == []


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


@pytest.mark.asyncio
async def test_the_recheck_does_not_free_a_waitlisted_book():
    """A return does not mean available: with people queued, the freed copy goes
    to the head of the waitlist and the book stays unborrowable.

    The follower already declines to write on a release, so the mark survives
    the return. This pins the other half -- that the re-check, which is the only
    thing allowed to clear, also refuses. If it cleared here the book would be
    published as borrowable with a queue in front of it, and nothing would
    correct it: the re-check only ever clears."""
    mock_solr = MagicMock(spec=Solr)
    mock_solr.select_async.return_value = MagicMock(docs=[{"key": "/books/OL1M", "ia": ["bookabc"], "_root_": "/works/OL1W", "loan_uid": 5}])
    with (
        patch("scripts.solr_updater.loan_availability_updater.get_solr", return_value=mock_solr),
        patch("openlibrary.core.lending.get_availability_async", return_value={"bookabc": WAITLISTED}),
    ):
        assert await build_recheck_updates() == []


@pytest.mark.asyncio
async def test_the_recheck_frees_the_book_once_the_queue_drains():
    """And the mark must not be permanent. The changes feed never reports a
    waitlist draining -- there is no event for it -- so the re-check is the only
    thing that can ever free this book. Same edition, same marked state, ground
    truth now says borrowable."""
    mock_solr = MagicMock(spec=Solr)
    mock_solr.select_async.return_value = MagicMock(docs=[{"key": "/books/OL1M", "ia": ["bookabc"], "_root_": "/works/OL1W", "loan_uid": 5}])
    with (
        patch("scripts.solr_updater.loan_availability_updater.get_solr", return_value=mock_solr),
        patch("openlibrary.core.lending.get_availability_async", return_value={"bookabc": AVAILABLE}),
    ):
        assert await build_recheck_updates() == [{"key": "/books/OL1M", "_root_": "/works/OL1W", "ebook_unavailable": {"set": EBOOK_AVAILABLE}}]


def test_a_return_on_a_waitlisted_book_leaves_the_mark_alone():
    """End to end on the follower side, for the exact sequence a reviewer
    worries about: borrow, then return, while a queue exists."""
    borrow = {"identifier": "bookabc", "uid": 100, "event_type": "borrow", "extra": '{"until": "2026-05-15 10:00:00"}'}
    assert build_solr_updates(collect_dirty_identifiers([borrow]), ID_TO_EDITION)[0]["ebook_unavailable"] == {"set": EBOOK_UNAVAILABLE}

    ret = {"identifier": "bookabc", "uid": 200, "event_type": "return", "extra": "{}"}
    assert build_solr_updates(collect_dirty_identifiers([ret]), ID_TO_EDITION) == []


# ---------------------------------------------------------------------------
# Index seed + overlap replay
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("scripts.solr_updater.loan_availability_updater.get_solr")
@patch("scripts.solr_updater.loan_availability_updater.init_sentry")
@patch("scripts.solr_updater.loan_availability_updater.lending")
@patch("scripts.solr_updater.loan_availability_updater.infogami")
@patch("scripts.solr_updater.loan_availability_updater.load_config")
async def test_the_index_set_is_never_written_without_ground_truth(mock_config, mock_infogami, mock_lending, mock_sentry, mock_get_solr, tmp_path):
    """The seed is a CANDIDATE set, not an answer.

    The search index is a lagged view and has been observed disagreeing with
    live availability on neighbouring lending fields. Writing it straight to
    Solr would publish availability nothing had checked -- including the unsafe
    direction, a book the index thinks is out that is actually borrowable.

    Here the index offers two books and ground truth says one of them is free.
    Only the other may be marked."""
    solr = MagicMock(spec=Solr)
    mock_get_solr.return_value = solr
    solr.select_async.side_effect = _select_side_effect
    solr.update_in_place_async.return_value = _OK_RESPONSE

    mock_lending.get_checked_out_candidates_async = AsyncMock(return_value=["bookabc", "bookxyz"])
    mock_lending.get_availability_async = AsyncMock(return_value={"bookabc": UNAVAILABLE, "bookxyz": AVAILABLE})
    mock_lending.is_available_for_loan.side_effect = lambda a: bool(a.get("available_to_browse") or a.get("available_to_borrow"))
    mock_lending.get_loan_changes = AsyncMock(
        side_effect=[
            {"status": "OK", "rows": [], "latest_uid": 100},
            {"status": "OK", "rows": [], "latest_uid": 100},
            SystemExit(0),
        ]
    )

    with pytest.raises(SystemExit):
        await main("fake_config.yml", state_file=str(tmp_path / "state"), poll_interval=0, recheck_interval=10_000)

    written = solr.update_in_place_async.call_args_list[0].args[0]
    assert [u["key"] for u in written] == ["/books/OL1M"], "the index's candidate that ground truth cleared must not be marked"


@pytest.mark.asyncio
@patch("scripts.solr_updater.loan_availability_updater.get_solr")
@patch("scripts.solr_updater.loan_availability_updater.init_sentry")
@patch("scripts.solr_updater.loan_availability_updater.lending")
@patch("scripts.solr_updater.loan_availability_updater.infogami")
@patch("scripts.solr_updater.loan_availability_updater.load_config")
async def test_the_overlap_replay_catches_a_borrow_the_snapshot_missed(mock_config, mock_infogami, mock_lending, mock_sentry, mock_get_solr, tmp_path):
    """The reason the overlap exists.

    The index snapshot is computed at an unknown instant. A book borrowed just
    after it is absent from the seed, so without a replay it stays unmarked and
    is published as borrowable while it is out -- the direction nothing
    recovers from, since the re-check only inspects books already marked."""
    solr = MagicMock(spec=Solr)
    mock_get_solr.return_value = solr
    solr.select_async.side_effect = _select_side_effect
    solr.update_in_place_async.return_value = _OK_RESPONSE

    mock_lending.get_checked_out_candidates_async = AsyncMock(return_value=[])  # snapshot missed it
    mock_lending.get_availability_async = AsyncMock(return_value={})
    mock_lending.get_loan_changes = AsyncMock(
        side_effect=[
            {"status": "OK", "rows": [], "latest_uid": 100},  # head probe
            {"status": "OK", "rows": [_BORROW_ROW], "latest_uid": 100},  # the missed borrow
            {"status": "OK", "rows": [], "latest_uid": 100},
            SystemExit(0),
        ]
    )

    with pytest.raises(SystemExit):
        await main("fake_config.yml", state_file=str(tmp_path / "state"), poll_interval=0, recheck_interval=10_000)

    marked = [u for call in solr.update_in_place_async.call_args_list for u in call.args[0]]
    assert any(u["ebook_unavailable"] == {"set": EBOOK_UNAVAILABLE} for u in marked), "the overlap replay did not mark the borrow the snapshot missed"


@pytest.mark.asyncio
@patch("scripts.solr_updater.loan_availability_updater.get_solr")
@patch("scripts.solr_updater.loan_availability_updater.init_sentry")
@patch("scripts.solr_updater.loan_availability_updater.lending")
@patch("scripts.solr_updater.loan_availability_updater.infogami")
@patch("scripts.solr_updater.loan_availability_updater.load_config")
async def test_the_overlap_replay_does_not_consult_availability(mock_config, mock_infogami, mock_lending, mock_sentry, mock_get_solr, tmp_path):
    """The replay uses the event path on purpose.

    Routing it through the reconcile instead would mean one availability
    request per hundred identifiers in the window -- at the feed's rate that
    reintroduces the unbounded cost the index seed exists to remove. The event
    path only marks, so its error is the recoverable one."""
    solr = MagicMock(spec=Solr)
    mock_get_solr.return_value = solr
    solr.select_async.side_effect = _select_side_effect
    solr.update_in_place_async.return_value = _OK_RESPONSE

    mock_lending.get_checked_out_candidates_async = AsyncMock(return_value=[])
    mock_lending.get_availability_async = AsyncMock(return_value={})
    mock_lending.get_loan_changes = AsyncMock(
        side_effect=[
            {"status": "OK", "rows": [], "latest_uid": 100},
            {"status": "OK", "rows": [_BORROW_ROW], "latest_uid": 100},
            {"status": "OK", "rows": [], "latest_uid": 100},
            SystemExit(0),
        ]
    )

    with pytest.raises(SystemExit):
        await main("fake_config.yml", state_file=str(tmp_path / "state"), poll_interval=0, recheck_interval=10_000)

    # The empty seed means the reconcile short-circuits without asking; the
    # replay must not ask either.
    mock_lending.get_availability_async.assert_not_called()


def test_the_overlap_window_is_bounded_by_events_not_time():
    """A time window converts to an unknown number of feed pages, which is the
    unbounded shape the index seed was adopted to remove."""
    assert isinstance(OVERLAP_EVENTS, int)
    pages = OVERLAP_EVENTS / BATCH_SIZE
    assert pages <= 100, f"{pages:.0f} feed pages is too much work for a startup overlap"
    hours = 24 * OVERLAP_EVENTS / LOAN_EVENTS_PER_DAY
    assert 1 <= hours <= 24, f"overlap of ~{hours:.1f}h is outside a sane range for index lag"
