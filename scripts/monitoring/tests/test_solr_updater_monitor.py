import json
import re
from datetime import datetime
from unittest.mock import patch

import pytest

from scripts.monitoring.solr_updater_monitor import monitor_solr_updater

DUMMY_OFFSET = "2025-09-20:49255084"


def patch_bash_run(commands: dict[str | re.Pattern[str], str]):
    def fake_bash_run(cmd, capture_output=False, sources=None):
        for pattern, response in commands.items():
            if (
                isinstance(pattern, re.Pattern) and pattern.match(cmd)
            ) or pattern == cmd:
                return response if capture_output else None
        raise AssertionError(f"Unexpected bash_run call: {cmd}")

    return patch('scripts.monitoring.solr_updater_monitor.bash_run', fake_bash_run)


def patch_httpx_get(responses: dict[str | re.Pattern[str], str]):
    class FakeResponse:
        def __init__(self, text):
            self._text = text

        def raise_for_status(self):
            pass

        def json(self):
            return json.loads(self._text)

    async def fake_httpx_get(client, url, *args, **kwargs):
        for pattern, response in responses.items():
            if (
                isinstance(pattern, re.Pattern) and pattern.match(url)
            ) or pattern == url:
                return FakeResponse(response)
        raise AssertionError(f"Unexpected httpx.get call: {url}")

    return patch(
        'scripts.monitoring.solr_updater_monitor.httpx.AsyncClient.get', fake_httpx_get
    )


@pytest.mark.asyncio
async def test_container_not_running(capsys):
    fake_bash: dict[str | re.Pattern[str], str] = {
        re.compile(r'^docker ps .*'): "some-other-container\nopenlibrary-web-1",
    }
    with patch_bash_run(fake_bash):
        await monitor_solr_updater(dry_run=True)

    out = capsys.readouterr().out
    assert "Container openlibrary-solr-updater-1 not running" in out


@pytest.mark.asyncio
async def test_container_running(capsys):
    fake_bash: dict[str | re.Pattern[str], str] = {
        re.compile(r'^docker ps .*'): "openlibrary-solr-updater-1",
        re.compile(r'^docker exec .*'): DUMMY_OFFSET,
    }
    fake_requests: dict[str | re.Pattern[str], str] = {
        f'http://ol-home.us.archive.org:7000/openlibrary.org/log/{DUMMY_OFFSET}?limit=1': json.dumps(
            {
                "data": [
                    {
                        "action": "store.put",
                        "site": "openlibrary.org",
                        "timestamp": "2025-09-20T14:28:56.908366",
                        "data": {
                            # ...
                        },
                    }
                ],
                "offset": "2025-09-20:94419809",
            }
        )
    }
    now = datetime.fromisoformat("2025-09-20T14:28:56.908366").timestamp() + 64

    with (
        patch_bash_run(fake_bash),
        patch_httpx_get(fake_requests),
        patch('scripts.monitoring.solr_updater_monitor.time.time', return_value=now),
    ):
        await monitor_solr_updater(dry_run=True)

    out = capsys.readouterr().out
    assert out == f'stats.ol.solr-updater.seconds_behind 64 {int(now)}\n'
