import json

import pytest

from openlibrary.core import lending
from openlibrary.core.waitinglist import WaitingLoan


class TestWaitingLoan:
    def test_new(self, monkeypatch):
        user_key = '/people/user1'
        identifier = 'foobar'
        monkeypatch.setattr(
            lending.ia_lending_api, 'join_waitinglist', lambda identifier, userid: True
        )
        monkeypatch.setattr(
            lending.ia_lending_api, 'query', lambda **kw: [({'status': 'waiting'})]
        )
        # POSTs to api to add to waiting list, then queries ia_lending_api for the result
        w = WaitingLoan.new(
            user_key=user_key, identifier=identifier, itemname='@ol_foobar'
        )
        assert w is not None
        assert w['status'] == 'waiting'

    @pytest.mark.xfail(run=False)
    def test_update(self):
        w = WaitingLoan.new(user_key="U1", identifier="B1")
        assert w['status'] == 'waiting'
        w.update(status='available')
        assert w['status'] == 'available'

        w2 = WaitingLoan.find(user_key="U1", identifier="B1")
        assert w2['status'] == 'available'

    @pytest.mark.xfail(run=False)
    def test_dict(self):
        user_key = '/people/user1'
        book_key = '/books/OL1234M'
        w = WaitingLoan.new(user_key=user_key, identifier=book_key)
        # ensure that w.dict() is JSON-able
        json.dumps(w.dict())

    def test_prune_expired(self):
        # prune_expired does nothing now but 'return'
        assert WaitingLoan.prune_expired() is None
