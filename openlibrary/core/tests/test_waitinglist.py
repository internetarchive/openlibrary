from openlibrary.core.waitinglist import WaitingLoan
from openlibrary.core import db
import web
import datetime
import json
import pytest
from .. import lending

class TestWaitingLoan:
    def test_new(self, monkeypatch):
        user_key = '/people/user1'
        identifier = 'foobar'
        monkeypatch.setattr(lending.ia_lending_api, "query", lambda **kw: [({'status': 'waiting'})])
        # POSTs to api to add to waiting list, then queries ia_lending_api for the result
        w = WaitingLoan.new(user_key=user_key,
                        identifier=identifier)
        assert w is not None
        assert w['status'] == 'waiting'

    @pytest.mark.xfail(run=False)
    def test_update(self):
        w = WaitingLoan.new(user_key="U1", identifier="B1")
        assert w['status'] == 'waiting'
        w.update(status='avaialble')
        assert w['status'] == 'avaialble'

        w2 = WaitingLoan.find(user_key="U1", identifier="B1")
        assert w2['status'] == 'avaialble'

    @pytest.mark.xfail(run=False)
    def test_dict(self):
        user_key = '/people/user1'
        book_key = '/books/OL1234M'
        w = WaitingLoan.new(user_key=user_key, identifier=book_key)
        # ensure that w.dict() is JSON-able
        json.dumps(w.dict())

    def test_prune_expired(self):
        # prune_expired does nothing now but 'return'
        assert WaitingLoan.prune_expired() == None

