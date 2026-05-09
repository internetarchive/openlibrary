"""Tests for loan_availability_updater.py"""

import datetime
from unittest.mock import MagicMock, patch

from scripts.solr_updater.loan_availability_updater import (
    build_eviction_updates,
    build_solr_updates,
    find_start_uid,
    ia_until_to_solr_date,
    process_changes,
    read_state,
    write_state,
)

# ---------------------------------------------------------------------------
# State file helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# ia_until_to_solr_date
# ---------------------------------------------------------------------------


def test_ia_until_to_solr_date_valid():
    assert ia_until_to_solr_date("2026-05-01 15:42:43") == "2026-05-01T15:42:43Z"


def test_ia_until_to_solr_date_none():
    assert ia_until_to_solr_date(None) is None


def test_ia_until_to_solr_date_invalid():
    assert ia_until_to_solr_date("not-a-date") is None


# ---------------------------------------------------------------------------
# process_changes
# ---------------------------------------------------------------------------

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


def test_process_changes_single_borrow():
    result = process_changes([BORROW_ROW])
    assert result["bookabc"]["event_type"] == "borrow"
    assert result["bookabc"]["until"] == "2026-05-15 10:00:00"
    assert result["bookabc"]["uid"] == 100


def test_process_changes_latest_wins():
    """When the same identifier appears twice, the higher-uid event wins."""
    result = process_changes([BORROW_ROW, RETURN_ROW])
    assert result["bookabc"]["event_type"] == "return"
    assert result["bookabc"]["until"] is None


def test_process_changes_latest_wins_reverse_order():
    """Order in the list doesn't matter; uid comparison decides."""
    result = process_changes([RETURN_ROW, BORROW_ROW])
    assert result["bookabc"]["event_type"] == "return"


def test_process_changes_multiple_identifiers():
    result = process_changes([BORROW_ROW, BROWSE_ROW, RETURN_ROW, EXPIRE_ROW])
    assert result["bookabc"]["event_type"] == "return"
    assert result["bookxyz"]["event_type"] == "expire_browse"


def test_process_changes_until_not_set_for_ended_events():
    result = process_changes([RETURN_ROW])
    assert result["bookabc"]["until"] is None


def test_process_changes_bad_extra_json():
    row = dict(BORROW_ROW, extra="not-json")
    result = process_changes([row])
    assert result["bookabc"]["until"] is None


# ---------------------------------------------------------------------------
# build_solr_updates
# ---------------------------------------------------------------------------

ID_TO_WORK = {"bookabc": "/works/OL1W", "bookxyz": "/works/OL2W"}


def test_build_solr_updates_borrow():
    id_state = process_changes([BORROW_ROW])
    updates = build_solr_updates(id_state, ID_TO_WORK)
    assert len(updates) == 1
    u = updates[0]
    assert u["key"] == "/works/OL1W"
    assert u["ebook_availability"] == {"set": "unavailable"}
    assert u["ebook_becomes_available"] == {"set": "2026-05-15T10:00:00Z"}


def test_build_solr_updates_return():
    id_state = process_changes([RETURN_ROW])
    updates = build_solr_updates(id_state, ID_TO_WORK)
    assert len(updates) == 1
    u = updates[0]
    assert u["key"] == "/works/OL1W"
    assert u["ebook_availability"] == {"set": "available"}
    assert u["ebook_becomes_available"] == {"set": None}


def test_build_solr_updates_unknown_identifier_skipped():
    id_state = process_changes([BORROW_ROW])
    updates = build_solr_updates(id_state, {})  # no mapping
    assert updates == []


def test_build_solr_updates_mixed():
    id_state = process_changes([BORROW_ROW, BROWSE_ROW, RETURN_ROW, EXPIRE_ROW])
    updates = build_solr_updates(id_state, ID_TO_WORK)
    keys = {u["key"] for u in updates}
    assert "/works/OL1W" in keys
    assert "/works/OL2W" in keys
    for u in updates:
        if u["key"] == "/works/OL1W" or u["key"] == "/works/OL2W":
            assert u["ebook_availability"] == {"set": "available"}


# ---------------------------------------------------------------------------
# build_eviction_updates
# ---------------------------------------------------------------------------


def test_build_eviction_updates():
    mock_result = MagicMock()
    mock_result.docs = [{"key": "/works/OL99W"}, {"key": "/works/OL100W"}]

    with patch("scripts.solr_updater.loan_availability_updater.get_solr") as mock_get_solr:
        mock_get_solr.return_value.select.return_value = mock_result
        updates = build_eviction_updates()

    assert len(updates) == 2
    assert updates[0]["key"] == "/works/OL99W"
    assert updates[0]["ebook_availability"] == {"set": "available"}
    assert updates[0]["ebook_becomes_available"] == {"set": None}

    # Confirm the Solr query targets past-expiry docs
    call_kwargs = mock_get_solr.return_value.select.call_args
    assert "ebook_becomes_available:[* TO NOW]" in str(call_kwargs)


def test_build_eviction_updates_empty():
    mock_result = MagicMock()
    mock_result.docs = []

    with patch("scripts.solr_updater.loan_availability_updater.get_solr") as mock_get_solr:
        mock_get_solr.return_value.select.return_value = mock_result
        updates = build_eviction_updates()

    assert updates == []


# ---------------------------------------------------------------------------
# find_start_uid (binary search)
# ---------------------------------------------------------------------------


def _make_loan_changes_response(rows, latest_uid=500_000):
    return {"status": "OK", "latest_uid": latest_uid, "rows": rows}


def _ts(days_ago: float) -> str:
    dt = datetime.datetime.utcnow() - datetime.timedelta(days=days_ago)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def test_find_start_uid_no_history():
    with patch("scripts.solr_updater.loan_availability_updater.lending") as mock_lending:
        mock_lending.get_loan_changes.return_value = {"status": "OK", "latest_uid": 0, "rows": []}
        uid = find_start_uid()
    assert uid == 0


def test_find_start_uid_api_error():
    with patch("scripts.solr_updater.loan_availability_updater.lending") as mock_lending:
        mock_lending.get_loan_changes.return_value = {"status": "error"}
        uid = find_start_uid()
    assert uid == 0


def test_find_start_uid_converges():
    """Binary search should converge to a uid where records are ~14 days old."""
    call_count = 0

    def fake_changes(after_uid, limit):
        nonlocal call_count
        call_count += 1
        # Simulate: uid=0→500k, newer rows have higher uids.
        # Each unit of uid ≈ 1 minute of wall-clock time (roughly).
        # latest_uid = 500_000 ≈ 347 days of events at 1 uid/minute.
        latest = 500_000
        if after_uid >= latest:
            return {"status": "OK", "latest_uid": latest, "rows": []}
        # Approximate: uid 0 is 20 days ago, uid=latest is now.
        fraction = after_uid / latest
        days_ago = 20 * (1 - fraction)
        return {
            "status": "OK",
            "latest_uid": latest,
            "rows": [{"time": _ts(days_ago), "uid": after_uid + 1}],
        }

    with patch("scripts.solr_updater.loan_availability_updater.lending") as mock_lending:
        mock_lending.get_loan_changes.side_effect = fake_changes
        uid = find_start_uid(target_age_days=14)

    # The binary search should have converged reasonably quickly
    assert call_count <= 42  # initial probe + BINARY_SEARCH_ITERS
    # uid should correspond to roughly 14 days ago in our fake universe
    # (latest * (20-14)/20 = 500_000 * 0.3 = 150_000)
    assert 100_000 < uid < 200_000
