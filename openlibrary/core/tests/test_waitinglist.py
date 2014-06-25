from openlibrary.core.waitinglist import WaitingLoan
from openlibrary.core import db
import web
import datetime
import json

class TestWaitingLoan:
    def setup_method(self, method):
        web.config.db_parameters = dict(dbn='postgres', db='oltest')
        db.query("TRUNCATE waitingloan")

    def test_new(self):
        book_key = '/books/OL1234M'
        user_key = '/people/user1'
        WaitingLoan.new(book_key=book_key, 
                        user_key=user_key)
        
        w = WaitingLoan.find(book_key=book_key, user_key=user_key)
        assert w is not None
        assert w['status'] == 'waiting'
        assert w['book_key'] == book_key
        assert w['user_key'] == user_key
        assert isinstance(w['since'], datetime.datetime)
        assert isinstance(w['last_update'], datetime.datetime)
        assert w['expiry'] is None
        assert w['available_email_sent'] is False

    def test_dict(self):
        user_key = '/people/user1'
        book_key = '/books/OL1234M'
        w = WaitingLoan.new(user_key=user_key, book_key=book_key)
        # ensure that w.dict() is JSON-able
        json.dumps(w.dict())
