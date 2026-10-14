from types import SimpleNamespace
from unittest.mock import patch

import pytest

from infogami import config
from openlibrary.core import async_db, fulltext
from openlibrary.core.jinja import get_jinja_env
from openlibrary.tests.core.async_db_fakes import FakeConnection, FakeConnectionContext
from openlibrary.utils import server_timing


@pytest.fixture
def timings():
    timings, token = server_timing.start_request()
    yield timings
    server_timing.end_request(token)


@pytest.mark.asyncio
async def test_async_db(timings):
    async def pool_for_loop():
        return SimpleNamespace(connection=lambda: FakeConnectionContext(FakeConnection()))

    with patch.object(async_db, "_pool_for_loop", pool_for_loop):
        await async_db.execute("SELECT 1")
    assert timings.snapshot()["db"][0] == 1


@pytest.mark.asyncio
@pytest.mark.usefixtures("request_context_fixture")
async def test_archive_org_failure(timings, httpx_mock, monkeypatch):
    monkeypatch.setattr(config, "plugin_inside", {"search_endpoint": "https://be-api.us.archive.org/fts/v1/search"}, raising=False)
    httpx_mock.add_response(status_code=503)
    await fulltext.fulltext_search_api({"q": "hello"})
    assert timings.snapshot()["ia-fts"][::2] == (1, 1)


def test_jinja_render(timings):
    get_jinja_env().from_string("{{ x }}").render(x=1)
    assert timings.snapshot()["render"][0] == 1
