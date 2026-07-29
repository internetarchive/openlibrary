"""Tests for loan_availability_updater.py"""

import datetime
from unittest.mock import MagicMock, patch

import pytest

from scripts.solr_updater.loan_availability_updater import (
    EBOOK_AVAILABLE,
    EBOOK_UNAVAILABLE,
    build_eviction_updates,
    build_solr_updates,
    find_start_uid,
    ia_until_to_epoch,
    main,
    process_changes,
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
    updates = build_solr_updates(process_changes([BORROW_ROW]), ID_TO_EDITION)
    assert len(updates) == 1
    assert updates[0] == {
        "key": "/books/OL1M",
        "_root_": "/works/OL1W",
        "ebook_availability": {"set": EBOOK_UNAVAILABLE},
        "ebook_becomes_available": {"set": ia_until_to_epoch("2026-05-15 10:00:00")},
        "loan_uid": {"set": 100},
    }


def test_build_solr_updates_return():
    """ebook_becomes_available is NOT included -- requireInPlace rejects "set": null
    unconditionally, so a return/expire event leaves it at its (now stale) prior value."""
    updates = build_solr_updates(process_changes([RETURN_ROW]), ID_TO_EDITION)
    assert len(updates) == 1
    assert updates[0] == {
        "key": "/books/OL1M",
        "_root_": "/works/OL1W",
        "ebook_availability": {"set": EBOOK_AVAILABLE},
        "loan_uid": {"set": 200},
    }
    assert "ebook_becomes_available" not in updates[0]


def test_build_solr_updates_unknown_identifier_skipped():
    assert build_solr_updates(process_changes([BORROW_ROW]), {}) == []


def test_build_solr_updates_mixed():
    updates = build_solr_updates(process_changes([BORROW_ROW, BROWSE_ROW, RETURN_ROW, EXPIRE_ROW]), ID_TO_EDITION)
    by_key = {u["key"]: u for u in updates}
    assert by_key["/books/OL1M"]["ebook_availability"] == {"set": EBOOK_AVAILABLE}
    assert by_key["/books/OL2M"]["ebook_availability"] == {"set": EBOOK_AVAILABLE}
    assert by_key["/books/OL1M"]["_root_"] == "/works/OL1W"
    assert by_key["/books/OL2M"]["_root_"] == "/works/OL2W"
    assert by_key["/books/OL1M"]["loan_uid"] == {"set": 200}
    assert by_key["/books/OL2M"]["loan_uid"] == {"set": 300}


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


def test_resolve_edition_keys_empty():
    assert resolve_edition_keys([]) == {}


def test_resolve_edition_keys_basic():
    mock_result = MagicMock()
    mock_result.docs = [
        {"key": "/books/OL1M", "ia": ["bookabc", "bookdef"], "_root_": "/works/OL1W"},
        {"key": "/books/OL2M", "ia": ["bookxyz"], "_root_": "/works/OL2W"},
    ]
    with patch("scripts.solr_updater.loan_availability_updater.get_solr") as mock_get_solr:
        mock_get_solr.return_value.select.return_value = mock_result
        result = resolve_edition_keys(["bookabc", "bookxyz"])

    assert result == {
        "bookabc": {"key": "/books/OL1M", "root": "/works/OL1W"},
        "bookxyz": {"key": "/books/OL2M", "root": "/works/OL2W"},
    }
    call_args = str(mock_get_solr.return_value.select.call_args)
    # Must scope to edition docs -- a flat ia:(...) query would also match the
    # parent work's aggregate ia field.
    assert "type:edition" in call_args
    # Identifiers must be quoted in the Solr query
    assert '"bookabc"' in call_args
    assert '"bookxyz"' in call_args


def test_build_eviction_updates():
    mock_result = MagicMock()
    mock_result.docs = [
        {"key": "/books/OL99M", "_root_": "/works/OL99W"},
        {"key": "/books/OL100M", "_root_": "/works/OL100W"},
    ]

    with (
        patch("scripts.solr_updater.loan_availability_updater.get_solr") as mock_get_solr,
        patch("scripts.solr_updater.loan_availability_updater.time") as mock_time,
    ):
        mock_time.time.return_value = 1_800_000_000
        mock_get_solr.return_value.select.return_value = mock_result
        updates = build_eviction_updates()

    assert updates == [
        {
            "key": "/books/OL99M",
            "_root_": "/works/OL99W",
            "ebook_availability": {"set": EBOOK_AVAILABLE},
        },
        {
            "key": "/books/OL100M",
            "_root_": "/works/OL100W",
            "ebook_availability": {"set": EBOOK_AVAILABLE},
        },
    ]
    call_args = str(mock_get_solr.return_value.select.call_args)
    assert "type:edition" in call_args
    # Scoped to currently-unavailable editions -- ebook_becomes_available can never be
    # cleared in-place, so this filter is what stops an available edition's stale
    # timestamp from matching this query forever.
    assert f"ebook_availability:{EBOOK_UNAVAILABLE}" in call_args
    assert "ebook_becomes_available:[* TO 1800000000]" in call_args


def test_build_eviction_updates_empty():
    mock_result = MagicMock()
    mock_result.docs = []
    with patch("scripts.solr_updater.loan_availability_updater.get_solr") as mock_get_solr:
        mock_get_solr.return_value.select.return_value = mock_result
        assert build_eviction_updates() == []


def test_solr_update_in_place_success_does_not_raise():
    with patch("scripts.solr_updater.loan_availability_updater.get_solr") as mock_get_solr:
        mock_get_solr.return_value.update_in_place.return_value = {"responseHeader": {"status": 0}}
        solr_update_in_place([{"key": "/books/OL1M"}], commit=True)  # no exception


def test_solr_update_in_place_raises_on_nonzero_status():
    """The exact original bug: Solr can 400 on a rejected in-place update while
    update_in_place_async returns the parsed body without raising. This must
    surface as an exception here rather than being silently accepted."""
    with patch("scripts.solr_updater.loan_availability_updater.get_solr") as mock_get_solr:
        mock_get_solr.return_value.update_in_place.return_value = {
            "responseHeader": {"status": 400},
            "error": {"msg": "Can not satisfy 'update.partial.requireInPlace'"},
        }
        with pytest.raises(RuntimeError, match="Solr in-place update error"):
            solr_update_in_place([{"key": "/books/OL1M"}])


def test_solr_update_in_place_propagates_transport_errors():
    with patch("scripts.solr_updater.loan_availability_updater.get_solr") as mock_get_solr:
        mock_get_solr.return_value.update_in_place.side_effect = RuntimeError("Solr unreachable")
        with pytest.raises(RuntimeError, match="Solr unreachable"):
            solr_update_in_place([{"key": "/books/OL1M"}])


def _ts(days_ago: float) -> str:
    dt = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=days_ago)
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
_RESOLVE_RESULT.docs = [{"key": "/books/OL1M", "ia": ["bookabc"], "_root_": "/works/OL1W"}]
_EMPTY_RESULT = MagicMock()
_EMPTY_RESULT.docs = []
_EVICT_RESULT = MagicMock()
_EVICT_RESULT.docs = [{"key": "/books/OL99M", "_root_": "/works/OL99W"}]

_OK_RESPONSE = {"responseHeader": {"status": 0}}


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
def test_main_calls_update_in_place_not_bare_update(mock_config, mock_infogami, mock_lending, mock_sentry, mock_time_mod, mock_get_solr, tmp_path):
    """The daemon must call update_in_place(), never bare update(), at all Solr write sites --
    ebook_availability/ebook_becomes_available are numeric specifically so this is possible."""
    solr = MagicMock()
    mock_get_solr.return_value = solr
    solr.select.side_effect = _select_side_effect
    solr.update_in_place.return_value = _OK_RESPONSE

    _run_main_one_iteration(tmp_path, solr, mock_lending, [_RETURN_ROW])

    assert solr.update_in_place.called, "update_in_place() was never called"
    solr.update.assert_not_called()


@patch("scripts.solr_updater.loan_availability_updater.get_solr")
@patch("scripts.solr_updater.loan_availability_updater.time")
@patch("scripts.solr_updater.loan_availability_updater.init_sentry")
@patch("scripts.solr_updater.loan_availability_updater.lending")
@patch("scripts.solr_updater.loan_availability_updater.infogami")
@patch("scripts.solr_updater.loan_availability_updater.load_config")
def test_main_update_transport_failure_does_not_advance_state(mock_config, mock_infogami, mock_lending, mock_sentry, mock_time_mod, mock_get_solr, tmp_path):
    """If the Solr update_in_place call raises (transport/connection failure), the state file must NOT be advanced."""
    solr = MagicMock()
    mock_get_solr.return_value = solr
    solr.select.side_effect = _select_side_effect
    solr.update_in_place.side_effect = RuntimeError("Solr unreachable")

    state_file = _run_main_one_iteration(tmp_path, solr, mock_lending, [_RETURN_ROW])

    assert state_file.read_text().strip() == "99", "write_state was called even though the Solr update failed"


@patch("scripts.solr_updater.loan_availability_updater.get_solr")
@patch("scripts.solr_updater.loan_availability_updater.time")
@patch("scripts.solr_updater.loan_availability_updater.init_sentry")
@patch("scripts.solr_updater.loan_availability_updater.lending")
@patch("scripts.solr_updater.loan_availability_updater.infogami")
@patch("scripts.solr_updater.loan_availability_updater.load_config")
def test_main_update_nonzero_status_does_not_advance_state(mock_config, mock_infogami, mock_lending, mock_sentry, mock_time_mod, mock_get_solr, tmp_path):
    """The original bug reproduced and guarded against: Solr responds with a non-zero
    responseHeader.status (e.g. a rejected in-place update) without the HTTP layer
    raising. This must still be treated as a failure -- state must NOT be advanced."""
    solr = MagicMock()
    mock_get_solr.return_value = solr
    solr.select.side_effect = _select_side_effect
    solr.update_in_place.return_value = {"responseHeader": {"status": 400}, "error": {"msg": "rejected"}}

    state_file = _run_main_one_iteration(tmp_path, solr, mock_lending, [_RETURN_ROW])

    assert state_file.read_text().strip() == "99", "write_state was called even though Solr reported a non-zero status"


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

    def update_in_place_side_effect(docs, commit=False):
        update_call_count[0] += 1
        if update_call_count[0] == 2:
            # Second call is the eviction update — make it fail
            raise RuntimeError("transient Solr error")
        # First call (main updates) and third call (commit) succeed
        return _OK_RESPONSE

    solr.update_in_place.side_effect = update_in_place_side_effect

    state_file = _run_main_one_iteration(tmp_path, solr, mock_lending, [_RETURN_ROW])

    # State must be advanced to 100 despite the eviction failure
    assert state_file.read_text().strip() == "100", "write_state was NOT called even though only eviction (non-fatal) failed"


@patch("scripts.solr_updater.loan_availability_updater.get_solr")
@patch("scripts.solr_updater.loan_availability_updater.find_start_uid")
@patch("scripts.solr_updater.loan_availability_updater.query_solr_uid")
@patch("scripts.solr_updater.loan_availability_updater.time")
@patch("scripts.solr_updater.loan_availability_updater.init_sentry")
@patch("scripts.solr_updater.loan_availability_updater.lending")
@patch("scripts.solr_updater.loan_availability_updater.infogami")
@patch("scripts.solr_updater.loan_availability_updater.load_config")
def test_main_reset_ignores_stale_solr_loan_uid(
    mock_config, mock_infogami, mock_lending, mock_sentry, mock_time_mod, mock_query_uid, mock_find_start, mock_get_solr, tmp_path
):
    """--reset must rebuild via find_start_uid (binary-search), never resume from a stale
    loan_uid still in Solr. Regression: query_solr_uid() used to run even under --reset and
    silently short-circuit the documented 14-day rebuild."""
    mock_query_uid.return_value = 200001  # stale high uid lingering in Solr
    mock_find_start.return_value = 42
    solr = MagicMock()
    mock_get_solr.return_value = solr
    solr.select.side_effect = _select_side_effect
    mock_lending.get_loan_changes.side_effect = SystemExit(0)  # stop right after startup init

    state_file = tmp_path / "state"
    with pytest.raises(SystemExit):
        main("fake_config.yml", state_file=str(state_file), poll_interval=0, reset=True)

    mock_query_uid.assert_not_called()
    mock_find_start.assert_called_once()
    assert state_file.read_text().strip() == "42", "reset resumed from stale Solr loan_uid instead of binary-searching"
