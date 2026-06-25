"""Tests for loan_availability_updater.py"""

import datetime
from unittest.mock import MagicMock, patch

import pytest

from scripts.solr_updater.loan_availability_updater import (
    build_eviction_updates,
    build_solr_updates,
    find_start_uid,
    ia_until_to_solr_date,
    main,
    process_changes,
    query_solr_uid,
    read_state,
    resolve_work_keys,
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


def test_ia_until_to_solr_date_valid():
    assert ia_until_to_solr_date("2026-05-01 15:42:43") == "2026-05-01T15:42:43Z"


def test_ia_until_to_solr_date_none():
    assert ia_until_to_solr_date(None) is None


def test_ia_until_to_solr_date_invalid():
    assert ia_until_to_solr_date("not-a-date") is None


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
ID_TO_WORK = {"bookabc": "/works/OL1W", "bookxyz": "/works/OL2W"}


def test_process_changes_single_borrow():
    result = process_changes([BORROW_ROW])
    assert result["bookabc"]["event_type"] == "borrow"
    assert result["bookabc"]["until"] == "2026-05-15 10:00:00"
    assert result["bookabc"]["uid"] == 100


def test_process_changes_latest_uid_wins():
    result = process_changes([BORROW_ROW, RETURN_ROW])
    assert result["bookabc"]["event_type"] == "return"
    assert result["bookabc"]["until"] is None


def test_process_changes_latest_uid_wins_reverse_order():
    result = process_changes([RETURN_ROW, BORROW_ROW])
    assert result["bookabc"]["event_type"] == "return"


def test_process_changes_multiple_identifiers():
    result = process_changes([BORROW_ROW, BROWSE_ROW, RETURN_ROW, EXPIRE_ROW])
    assert result["bookabc"]["event_type"] == "return"
    assert result["bookxyz"]["event_type"] == "expire_browse"


def test_process_changes_no_until_for_ended_events():
    assert process_changes([RETURN_ROW])["bookabc"]["until"] is None


def test_process_changes_bad_extra_json():
    result = process_changes([dict(BORROW_ROW, extra="not-json")])
    assert result["bookabc"]["until"] is None


def test_build_solr_updates_borrow():
    updates = build_solr_updates(process_changes([BORROW_ROW]), ID_TO_WORK)
    assert len(updates) == 1
    assert updates[0] == {
        "key": "/works/OL1W",
        "ebook_availability": {"set": "unavailable"},
        "ebook_becomes_available": {"set": "2026-05-15T10:00:00Z"},
        "loan_uid": {"set": 100},
    }


def test_build_solr_updates_return():
    updates = build_solr_updates(process_changes([RETURN_ROW]), ID_TO_WORK)
    assert len(updates) == 1
    assert updates[0] == {
        "key": "/works/OL1W",
        "ebook_availability": {"set": "available"},
        "ebook_becomes_available": {"set": None},
        "loan_uid": {"set": 200},
    }


def test_build_solr_updates_unknown_identifier_skipped():
    assert build_solr_updates(process_changes([BORROW_ROW]), {}) == []


def test_build_solr_updates_mixed():
    updates = build_solr_updates(process_changes([BORROW_ROW, BROWSE_ROW, RETURN_ROW, EXPIRE_ROW]), ID_TO_WORK)
    by_key = {u["key"]: u for u in updates}
    assert by_key["/works/OL1W"]["ebook_availability"] == {"set": "available"}
    assert by_key["/works/OL2W"]["ebook_availability"] == {"set": "available"}
    assert by_key["/works/OL1W"]["loan_uid"] == {"set": 200}
    assert by_key["/works/OL2W"]["loan_uid"] == {"set": 300}


def test_query_solr_uid_with_data():
    mock_result = MagicMock()
    mock_result.docs = [{"loan_uid": 42000}]
    with patch("scripts.solr_updater.loan_availability_updater.get_solr") as mock_get_solr:
        mock_get_solr.return_value.select.return_value = mock_result
        assert query_solr_uid() == 42000
    call_args = str(mock_get_solr.return_value.select.call_args)
    assert "loan_uid desc" in call_args


def test_query_solr_uid_empty():
    mock_result = MagicMock()
    mock_result.docs = []
    with patch("scripts.solr_updater.loan_availability_updater.get_solr") as mock_get_solr:
        mock_get_solr.return_value.select.return_value = mock_result
        assert query_solr_uid() == 0


def test_resolve_work_keys_empty():
    assert resolve_work_keys([]) == {}


def test_resolve_work_keys_basic():
    mock_result = MagicMock()
    mock_result.docs = [
        {"key": "/works/OL1W", "ia": ["bookabc", "bookdef"]},
        {"key": "/works/OL2W", "ia": ["bookxyz"]},
    ]
    with patch("scripts.solr_updater.loan_availability_updater.get_solr") as mock_get_solr:
        mock_get_solr.return_value.select.return_value = mock_result
        result = resolve_work_keys(["bookabc", "bookxyz"])

    assert result == {"bookabc": "/works/OL1W", "bookxyz": "/works/OL2W"}
    # Identifiers must be quoted in the Solr query
    call_args = str(mock_get_solr.return_value.select.call_args)
    assert '"bookabc"' in call_args
    assert '"bookxyz"' in call_args


def test_build_eviction_updates():
    mock_result = MagicMock()
    mock_result.docs = [{"key": "/works/OL99W"}, {"key": "/works/OL100W"}]

    with patch("scripts.solr_updater.loan_availability_updater.get_solr") as mock_get_solr:
        mock_get_solr.return_value.select.return_value = mock_result
        updates = build_eviction_updates()

    assert updates == [
        {"key": "/works/OL99W", "ebook_availability": {"set": "available"}, "ebook_becomes_available": {"set": None}},
        {"key": "/works/OL100W", "ebook_availability": {"set": "available"}, "ebook_becomes_available": {"set": None}},
    ]
    assert "ebook_becomes_available:[* TO NOW]" in str(mock_get_solr.return_value.select.call_args)


def test_build_eviction_updates_empty():
    mock_result = MagicMock()
    mock_result.docs = []
    with patch("scripts.solr_updater.loan_availability_updater.get_solr") as mock_get_solr:
        mock_get_solr.return_value.select.return_value = mock_result
        assert build_eviction_updates() == []


def _ts(days_ago: float) -> str:
    dt = datetime.datetime.utcnow() - datetime.timedelta(days=days_ago)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def test_find_start_uid_no_history():
    with patch("scripts.solr_updater.loan_availability_updater.lending") as mock_lending:
        mock_lending.get_loan_changes.return_value = {"status": "OK", "latest_uid": 0, "rows": []}
        assert find_start_uid() == 0


def test_find_start_uid_api_error():
    with patch("scripts.solr_updater.loan_availability_updater.lending") as mock_lending:
        mock_lending.get_loan_changes.return_value = {"status": "error"}
        assert find_start_uid() == 0


def test_find_start_uid_converges():
    """Binary search converges to a uid where the next record is ~14 days old."""
    call_count = 0

    def fake_changes(after_uid, limit):
        nonlocal call_count
        call_count += 1
        latest = 500_000
        if after_uid >= latest:
            return {"status": "OK", "latest_uid": latest, "rows": []}
        # uid 0 → 20 days ago, uid latest → now (linear approximation)
        days_ago = 20 * (1 - after_uid / latest)
        return {
            "status": "OK",
            "latest_uid": latest,
            "rows": [{"time": _ts(days_ago), "uid": after_uid + 1}],
        }

    with patch("scripts.solr_updater.loan_availability_updater.lending") as mock_lending:
        mock_lending.get_loan_changes.side_effect = fake_changes
        uid = find_start_uid(target_age_days=14)

    assert call_count <= 41  # 1 initial probe + up to 40 binary-search iterations
    # uid=150_000 is the exact 14-day boundary (500_000 * (20-14)/20 = 150_000)
    assert 100_000 < uid < 200_000


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
_RESOLVE_RESULT = MagicMock()
_RESOLVE_RESULT.docs = [{"key": "/works/OL1W", "ia": ["bookabc"]}]
_EMPTY_RESULT = MagicMock()
_EMPTY_RESULT.docs = []
_EVICT_RESULT = MagicMock()
_EVICT_RESULT.docs = [{"key": "/works/OL99W"}]


def _select_side_effect(*args, **kwargs):
    """Route Solr select calls to the right fixture by query content."""
    query = kwargs.get("query", "") or (args[0] if args else "")
    if "loan_uid" in query:
        return _EMPTY_RESULT
    if "ia:" in query:
        return _RESOLVE_RESULT
    # ebook_becomes_available range query → evictions (empty unless overridden)
    return _EMPTY_RESULT


def _run_main_one_iteration(tmp_path, solr_mock, lending_mock, first_batch_rows):
    """Run main() through exactly one event-processing iteration."""
    state_file = tmp_path / "state"
    state_file.write_text("99")  # pre-seed so we skip startup init

    lending_mock.get_loan_changes.side_effect = [
        {"status": "OK", "rows": first_batch_rows, "latest_uid": 100},
        SystemExit(0),  # stop the loop on the second iteration
    ]

    with pytest.raises(SystemExit):
        main("fake_config.yml", state_file=str(state_file), poll_interval=0)

    return state_file


@patch("scripts.solr_updater.loan_availability_updater.get_solr")
@patch("scripts.solr_updater.loan_availability_updater.time")
@patch("scripts.solr_updater.loan_availability_updater.init_sentry")
@patch("scripts.solr_updater.loan_availability_updater.lending")
@patch("scripts.solr_updater.loan_availability_updater.infogami")
@patch("scripts.solr_updater.loan_availability_updater.load_config")
def test_main_calls_update_not_update_in_place(mock_config, mock_infogami, mock_lending, mock_sentry, mock_time_mod, mock_get_solr, tmp_path):
    """The daemon must call update(), never update_in_place(), at all Solr write sites."""
    solr = MagicMock()
    mock_get_solr.return_value = solr
    solr.select.side_effect = _select_side_effect

    _run_main_one_iteration(tmp_path, solr, mock_lending, [_RETURN_ROW])

    # update() must have been called at least once (updates + commit)
    assert solr.update.called, "update() was never called"
    # update_in_place() must not be called from the daemon
    solr.update_in_place.assert_not_called()


@patch("scripts.solr_updater.loan_availability_updater.get_solr")
@patch("scripts.solr_updater.loan_availability_updater.time")
@patch("scripts.solr_updater.loan_availability_updater.init_sentry")
@patch("scripts.solr_updater.loan_availability_updater.lending")
@patch("scripts.solr_updater.loan_availability_updater.infogami")
@patch("scripts.solr_updater.loan_availability_updater.load_config")
def test_main_update_failure_does_not_advance_state(mock_config, mock_infogami, mock_lending, mock_sentry, mock_time_mod, mock_get_solr, tmp_path):
    """If the Solr update call raises, the state file must NOT be advanced."""
    solr = MagicMock()
    mock_get_solr.return_value = solr
    solr.select.side_effect = _select_side_effect
    # First update() call (the actual docs update) raises — simulates Solr down
    solr.update.side_effect = RuntimeError("Solr unreachable")

    state_file = _run_main_one_iteration(tmp_path, solr, mock_lending, [_RETURN_ROW])

    # State must still be 99 — the failed update prevented state advancement
    assert state_file.read_text().strip() == "99", "write_state was called even though the Solr update failed"


@patch("scripts.solr_updater.loan_availability_updater.get_solr")
@patch("scripts.solr_updater.loan_availability_updater.time")
@patch("scripts.solr_updater.loan_availability_updater.init_sentry")
@patch("scripts.solr_updater.loan_availability_updater.lending")
@patch("scripts.solr_updater.loan_availability_updater.infogami")
@patch("scripts.solr_updater.loan_availability_updater.load_config")
def test_main_eviction_failure_is_non_fatal(mock_config, mock_infogami, mock_lending, mock_sentry, mock_time_mod, mock_get_solr, tmp_path):
    """Eviction update failure must not prevent state advancement.

    Main updates already committed successfully; eviction is a safety net
    that retries automatically next cycle.
    """
    solr = MagicMock()
    mock_get_solr.return_value = solr

    # Route select to return an eviction candidate so we actually hit the eviction path
    def select_side_effect_with_eviction(*args, **kwargs):
        query = kwargs.get("query", "") or (args[0] if args else "")
        if "loan_uid" in query:
            return _EMPTY_RESULT
        if "ia:" in query:
            return _RESOLVE_RESULT
        # ebook_becomes_available range → one expired loan to evict
        return _EVICT_RESULT

    solr.select.side_effect = select_side_effect_with_eviction

    update_call_count = [0]

    def update_side_effect(docs, commit=False):
        update_call_count[0] += 1
        if update_call_count[0] == 2:
            # Second call is the eviction update — make it fail
            raise RuntimeError("transient Solr error")
        # First call (main updates) and third call (commit) succeed

    solr.update.side_effect = update_side_effect

    state_file = _run_main_one_iteration(tmp_path, solr, mock_lending, [_RETURN_ROW])

    # State must be advanced to 100 despite the eviction failure
    assert state_file.read_text().strip() == "100", "write_state was NOT called even though only eviction (non-fatal) failed"
