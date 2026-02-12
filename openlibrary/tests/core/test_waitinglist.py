"""Tests for WaitingLoan core functionality.

Waiting loans track users waiting for books that are currently checked out.
"""

import datetime
import json
from unittest.mock import Mock

import pytest

from openlibrary.core import lending
from openlibrary.core.waitinglist import WaitingLoan


class TestWaitingLoanNew:
    """Tests for creating new waiting loans."""

    def test_new_creates_waiting_loan(self, monkeypatch):
        """Test that creating a new waiting loan calls the IA API and returns a WaitingLoan."""
        user_key = '/people/user1'
        identifier = 'foobar'
        monkeypatch.setattr(
            lending.ia_lending_api, 'join_waitinglist', lambda identifier, userid: True
        )
        monkeypatch.setattr(
            lending.ia_lending_api, 'query', lambda **kw: [{'status': 'waiting'}]
        )
        # POSTs to api to add to waiting list, then queries ia_lending_api for the result
        w = WaitingLoan.new(
            user_key=user_key, identifier=identifier, itemname='@ol_foobar'
        )
        assert w is not None
        assert w['status'] == 'waiting'

    def test_new_returns_none_when_not_found(self, monkeypatch):
        """Test that new returns None when the loan isn't found after joining."""
        monkeypatch.setattr(
            lending.ia_lending_api, 'join_waitinglist', lambda identifier, userid: True
        )
        monkeypatch.setattr(lending.ia_lending_api, 'query', lambda **kw: [])

        w = WaitingLoan.new(
            user_key='/people/user1', identifier='foobar', itemname='@ol_foobar'
        )
        assert w is None


class TestWaitingLoanFind:
    """Tests for finding existing waiting loans."""

    def test_find_returns_waiting_loan(self, monkeypatch):
        """Test finding an existing waiting loan."""
        mock_loan = {
            'status': 'waiting',
            'identifier': 'book123',
            'userid': '@ol_user1',
        }

        monkeypatch.setattr(
            lending.ia_lending_api, 'query', lambda **kw: [mock_loan.copy()]
        )

        w = WaitingLoan.find(
            user_key='/people/user1', identifier='book123', itemname='@ol_user1'
        )
        assert w is not None
        assert w['status'] == 'waiting'
        assert w['identifier'] == 'book123'

    def test_find_returns_none_when_not_found(self, monkeypatch):
        """Test that find returns None when no matching loan exists."""
        monkeypatch.setattr(lending.ia_lending_api, 'query', lambda **kw: [])

        w = WaitingLoan.find(
            user_key='/people/user1', identifier='book123', itemname='@ol_user1'
        )
        assert w is None


class TestWaitingLoanUpdate:
    """Tests for updating waiting loans."""

    def test_update_modifies_status(self, monkeypatch):
        """Test that update correctly modifies the waiting loan status and calls the API."""
        mock_waiting_loan = {
            'status': 'waiting',
            'identifier': 'B1',
            'userid': '@ol_u1',
            'since': '2013-09-16T06:09:16.577942',
        }

        mock_update = Mock()
        monkeypatch.setattr(
            lending.ia_lending_api, 'join_waitinglist', lambda identifier, userid: True
        )
        monkeypatch.setattr(
            lending.ia_lending_api, 'query', lambda **kw: [mock_waiting_loan.copy()]
        )
        monkeypatch.setattr(lending.ia_lending_api, 'update_waitinglist', mock_update)

        w = WaitingLoan.new(user_key="/people/U1", identifier="B1", itemname="@ol_u1")
        assert w['status'] == 'waiting'

        w.update(status='available', email_sent=True)
        assert w['status'] == 'available'
        assert w['email_sent'] is True

        # Verify the API was called with correct params
        mock_update.assert_called_once_with(
            identifier='B1', userid='@ol_u1', status='available', email_sent=True
        )


class TestWaitingLoanIsExpired:
    """Tests for the is_expired method."""

    def test_is_expired_when_status_available_and_expiry_past(self):
        """Test that a loan is expired when status is available and expiry has passed."""
        # Use a past expiry date
        past_expiry = (
            datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
            - datetime.timedelta(hours=1)
        ).isoformat()

        w = WaitingLoan(
            {
                'status': 'available',
                'expiry': past_expiry,
            }
        )
        assert w.is_expired() is True

    def test_not_expired_when_status_waiting(self):
        """Test that a loan is not expired when status is waiting, regardless of expiry."""
        past_expiry = (
            datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
            - datetime.timedelta(hours=1)
        ).isoformat()

        w = WaitingLoan(
            {
                'status': 'waiting',
                'expiry': past_expiry,
            }
        )
        assert w.is_expired() is False

    def test_not_expired_when_expiry_future(self):
        """Test that a loan is not expired when expiry is in the future."""
        future_expiry = (
            datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
            + datetime.timedelta(hours=1)
        ).isoformat()

        w = WaitingLoan(
            {
                'status': 'available',
                'expiry': future_expiry,
            }
        )
        assert w.is_expired() is False

    def test_not_expired_when_no_expiry(self):
        """Test that a loan is not expired when there's no expiry date."""
        w = WaitingLoan({'status': 'available'})
        # This should raise KeyError, testing that expiry is required for this check
        with pytest.raises(KeyError):
            w.is_expired()


class TestWaitingLoanGetWaitingInDays:
    """Tests for the get_waiting_in_days method."""

    def test_waiting_in_days_for_new_loan(self):
        """Test that a new loan has waited 1 day (includes current day)."""
        today = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
        w = WaitingLoan({'since': today.isoformat()})
        # Should be 1 day because it adds 1 to round off
        assert w.get_waiting_in_days() == 1

    def test_waiting_in_days_for_week_old_loan(self):
        """Test calculating days waited for a loan from a week ago."""
        week_ago = datetime.datetime.now(datetime.UTC).replace(
            tzinfo=None
        ) - datetime.timedelta(days=7)
        w = WaitingLoan({'since': week_ago.isoformat()})
        # 7 days + 1 for rounding = 8
        assert w.get_waiting_in_days() == 8


class TestWaitingLoanGetExpiryInHours:
    """Tests for the get_expiry_in_hours method."""

    def test_expiry_in_hours_when_expiring_soon(self):
        """Test calculating hours until expiry for a loan expiring soon."""
        expiry_time = datetime.datetime.now(datetime.UTC).replace(
            tzinfo=None
        ) + datetime.timedelta(hours=2, minutes=30)
        w = WaitingLoan({'expiry': expiry_time.isoformat()})
        # Should be approximately 2.5 hours
        result = w.get_expiry_in_hours()
        assert 2.4 <= result <= 2.6

    def test_expiry_in_hours_when_expired(self):
        """Test that expired loans return 0 hours."""
        past_time = datetime.datetime.now(datetime.UTC).replace(
            tzinfo=None
        ) - datetime.timedelta(hours=5)
        w = WaitingLoan({'expiry': past_time.isoformat()})
        assert w.get_expiry_in_hours() == 0.0

    def test_expiry_in_hours_when_no_expiry(self):
        """Test that loans without expiry return 0 hours."""
        w = WaitingLoan({})
        assert w.get_expiry_in_hours() == 0.0

    def test_expiry_in_hours_clamps_negative_to_zero(self):
        """Test that a loan that just expired returns 0, not negative hours."""
        # A loan that expired 5 seconds ago
        five_seconds_ago = datetime.datetime.now(datetime.UTC).replace(
            tzinfo=None
        ) - datetime.timedelta(seconds=5)
        w = WaitingLoan({'expiry': five_seconds_ago.isoformat()})
        # Should be 0.0, not negative, due to max(0.0, ...)
        result = w.get_expiry_in_hours()
        assert result == 0.0


class TestWaitingLoanDict:
    """Tests for the dict method."""

    def test_dict_converts_datetime_to_iso_string(self):
        """Test that datetime objects are converted to ISO format strings."""
        dt = datetime.datetime(2023, 5, 15, 14, 30, 45)
        w = WaitingLoan({'since': dt, 'status': 'waiting'})

        result = w.dict()
        assert isinstance(result['since'], str)
        assert result['since'] == '2023-05-15T14:30:45'

    def test_dict_is_json_serializable(self):
        """Test that the dict output can be serialized to JSON."""
        dt = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
        w = WaitingLoan(
            {
                'status': 'waiting',
                'identifier': 'book123',
                'userid': '@ol_user1',
                'since': dt,
            }
        )

        result = w.dict()
        # This should not raise an exception
        json_str = json.dumps(result)
        assert isinstance(json_str, str)

    def test_dict_preserves_all_keys(self):
        """Test that dict() preserves all original keys."""
        w = WaitingLoan(
            {
                'status': 'waiting',
                'identifier': 'book123',
                'userid': '@ol_user1',
                'position': 5,
            }
        )

        result = w.dict()
        assert set(result.keys()) == {'status', 'identifier', 'userid', 'position'}


class TestWaitingLoanGetPosition:
    """Tests for the get_position method."""

    def test_get_position(self):
        """Test getting position in waiting list."""
        w = WaitingLoan({'position': 3})
        assert w.get_position() == 3


class TestWaitingLoanGetWaitinglistSize:
    """Tests for the get_waitinglist_size method."""

    def test_get_waitinglist_size(self):
        """Test getting the total waiting list size."""
        w = WaitingLoan({'wl_size': 42})
        assert w.get_waitinglist_size() == 42


class TestWaitingLoanDelete:
    """Tests for the delete method."""

    def test_delete_calls_api(self, monkeypatch):
        """Test that delete calls the IA lending API."""
        mock_leave = Mock()
        monkeypatch.setattr(lending.ia_lending_api, 'leave_waitinglist', mock_leave)

        w = WaitingLoan({'identifier': 'book123', 'userid': '@ol_user1'})
        w.delete()

        mock_leave.assert_called_once_with('book123', '@ol_user1')


class TestWaitingLoanGetUserKey:
    """Tests for the get_user_key method."""

    def test_get_user_key_returns_user_key_when_present(self):
        """Test that user_key is returned directly when already set."""
        w = WaitingLoan({'user_key': '/people/user1'})
        assert w.get_user_key() == '/people/user1'

    def test_get_user_key_parses_ol_prefix(self):
        """Test parsing userid with 'ol:' prefix."""
        w = WaitingLoan({'userid': 'ol:user1'})
        assert w.get_user_key() == '/people/user1'

    def test_get_user_key_handles_at_prefix(self, monkeypatch):
        """Test parsing userid with '@' prefix (requires account lookup)."""
        # Mock the account lookup
        mock_account = Mock()
        mock_account.username = 'user1'
        monkeypatch.setattr(
            'openlibrary.core.waitinglist.OpenLibraryAccount.get_or_raise',
            lambda userid, field: mock_account,
        )

        w = WaitingLoan({'userid': '@ol_user1'})
        assert w.get_user_key() == '/people/user1'
