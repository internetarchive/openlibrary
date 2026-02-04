from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from scripts.monitoring.haproxy_monitor import GraphiteEvent
from scripts.monitoring.solr_updater_monitor import get_solr_updater_lag_event


@pytest.mark.asyncio
async def test_get_solr_updater_lag_event(httpx_mock):
    """Test that solr updater lag is calculated correctly from ISO timestamps."""
    # Mock bash_run to return a fixed offset
    mock_bash_result = MagicMock()
    mock_bash_result.stdout = "2026-02-02:661542787\n"

    # Mock httpx response with ISO timestamp
    # Last processed: 2026-02-02 23:47:56 UTC
    for _ in range(2):  # Two calls: one for solr, one for solr_next
        httpx_mock.add_response(
            url="http://localhost:7000/openlibrary.org/log/2026-02-02:661542787?limit=1",
            json={
                "data": [
                    {
                        "action": "store.put",
                        "site": "openlibrary.org",
                        "timestamp": "2026-02-02T23:47:56.756852",
                        "data": {},
                    }
                ],
                "offset": "2026-02-02:661543070",
            },
        )

    # Mock time.time() to return "now": 2026-02-02 23:57:56 UTC (10 minutes after last processed)
    # Parse the ISO timestamp to get the exact epoch
    last_processed = datetime.fromisoformat("2026-02-02T23:47:56.756852")
    last_processed_epoch = int(last_processed.timestamp())
    now_epoch = last_processed_epoch + 600  # 10 minutes = 600 seconds later

    with (
        patch(
            'scripts.monitoring.solr_updater_monitor.bash_run',
            return_value=mock_bash_result,
        ),
        patch(
            'scripts.monitoring.solr_updater_monitor.time.time',
            return_value=now_epoch,
        ),
    ):
        event = await get_solr_updater_lag_event(solr_next=False)
        assert event == GraphiteEvent(
            path="stats.ol.solr.solr_updater_lag", value=600, timestamp=now_epoch
        )

        event = await get_solr_updater_lag_event(solr_next=True)
        assert event == GraphiteEvent(
            path="stats.ol.solr_next.solr_updater_lag", value=600, timestamp=now_epoch
        )
