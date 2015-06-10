from openlibrary.core.waitinglist import WaitingLoan
from openlibrary.core import db
import web
import datetime
import json
import pytest

@pytest.mark.xfail(run=False)
class TestWaitingLoan:
    def setup_method(self, method):
        web.config.db_parameters = dict(dbn='postgres', db='oltest')
        #db.query("TRUNCATE waitingloan")

    def test_new(self):
        book_key = '/books/OL1234M'
        user_key = '/people/user1'
        identifier = '/books/OL1234M'
        w = WaitingLoan.new(book_key=book_key,
                        user_key=user_key,
                        identifier=identifier)
        
        assert w is not None
        assert w['status'] == 'waiting'
        assert w['book_key'] == book_key
        assert w['user_key'] == user_key
        assert isinstance(w['since'], datetime.datetime)
        assert isinstance(w['last_update'], datetime.datetime)
        assert w['expiry'] is None
        assert w['available_email_sent'] is False

    def test_update(self):
        w = WaitingLoan.new(user_key="U1", book_key="B1")
        assert w['status'] == 'waiting'
        w.update(status='avaialble')
        assert w['status'] == 'avaialble'

        w2 = WaitingLoan.find(user_key="U1", book_key="B1")
        assert w2['status'] == 'avaialble'

    def test_dict(self):
        user_key = '/people/user1'
        book_key = '/books/OL1234M'
        w = WaitingLoan.new(user_key=user_key, book_key=book_key)
        # ensure that w.dict() is JSON-able
        json.dumps(w.dict())

    def test_prune_expired(self):
        now = datetime.datetime.utcnow()
        day = datetime.timedelta(days=1)

        # no expiry specified, should not be deleted.
        w1 = WaitingLoan.new(user_key="U1", book_key="B1")
        # going to expire in one more day
        w2 = WaitingLoan.new(user_key="U2", book_key="B2", expiry=now+day)
        # already expired one day ago
        w3 = WaitingLoan.new(user_key="U3", book_key="B3", expiry=now-day)

        assert WaitingLoan.prune_expired() == [w3]
        assert WaitingLoan.query() == [w1, w2]
