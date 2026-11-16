import asyncio
from unittest import mock

import pytest
import web

from openlibrary import accounts
from openlibrary.utils.request_context import site


class FakeConnection:
    def __init__(self, token=None):
        self.token = token

    def set_auth_token(self, token):
        self.token = token


class FakeSite:
    def __init__(self, conn):
        self._conn = conn


@pytest.fixture
def run_as_patron(monkeypatch):
    patron = mock.Mock()
    patron.generate_login_code.return_value = "patron-token"
    monkeypatch.setattr(accounts, "find", lambda username: patron)
    monkeypatch.setattr(accounts, "get_current_user", lambda: None)


@pytest.mark.asyncio
async def test_run_as_only_touches_its_own_requests_connection(monkeypatch, run_as_patron):
    # Under FastAPI every request shares the event-loop thread's web.ctx, so web.ctx.conn
    # belongs to whichever request last ran infogami's create_site, not necessarily this one.
    other_conn = FakeConnection("other-request-token")
    monkeypatch.setattr(web.ctx, "conn", other_conn, raising=False)
    own_conn = FakeConnection()
    entered = asyncio.Event()
    release = asyncio.Event()

    async def anonymize_request():
        site.set(FakeSite(own_conn))
        with accounts.RunAs("patron"):
            assert own_conn.token == "patron-token"
            entered.set()
            await release.wait()
        assert own_conn.token is None

    task = asyncio.create_task(anonymize_request())
    await entered.wait()
    # Another request is handled while RunAs is held across an await.
    assert other_conn.token == "other-request-token"
    release.set()
    await task
    assert other_conn.token == "other-request-token"
