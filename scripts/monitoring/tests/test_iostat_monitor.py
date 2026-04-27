import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scripts.monitoring.iostat_monitor import IOSTAT_COMMAND, get_iostat_events, get_iostat_payload
from scripts.monitoring.utils import GraphiteEvent

FAKE_IOSTAT_JSON = """
{
  "sysstat": {
    "hosts": [
      {
        "statistics": [
          {
            "avg-cpu": {
              "user": 58.80,
              "iowait": 5.48,
              "idle": 20.69
            },
            "disk": [
              {
                "disk_device": "vda",
                "r/s": 2395.37,
                "w/s": 17.57,
                "aqu-sz": 1.64,
                "util": 83.79
              }
            ]
          }
        ]
      }
    ]
  }
}
"""


@pytest.mark.asyncio
async def test_get_iostat_payload_runs_expected_command():
    mock_process = MagicMock()
    mock_process.communicate = AsyncMock(return_value=(FAKE_IOSTAT_JSON.encode("utf-8"), b""))
    mock_process.returncode = 0

    with patch("scripts.monitoring.iostat_monitor.asyncio.create_subprocess_exec", AsyncMock(return_value=mock_process)) as mock_create_process:
        payload = await get_iostat_payload()

    mock_create_process.assert_called_once_with(
        *IOSTAT_COMMAND,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    assert payload["sysstat"]["hosts"]


@pytest.mark.asyncio
async def test_get_iostat_events_generates_disk_and_cpu_events():
    with patch("scripts.monitoring.iostat_monitor.get_iostat_payload", AsyncMock(return_value=json.loads(FAKE_IOSTAT_JSON))):
        events = await get_iostat_events(bucket="stats.ol.ol-solr0", timestamp=1713859200)

        event_map = {event.path: event for event in events}

        assert event_map["stats.ol.ol-solr0.iostat.disk.vda.r_s"] == GraphiteEvent(
            path="stats.ol.ol-solr0.iostat.disk.vda.r_s",
            value=2395.37,
            timestamp=1713859200,
        )
        assert event_map["stats.ol.ol-solr0.iostat.disk.vda.w_s"] == GraphiteEvent(
            path="stats.ol.ol-solr0.iostat.disk.vda.w_s",
            value=17.57,
            timestamp=1713859200,
        )
        assert event_map["stats.ol.ol-solr0.iostat.disk.vda.aqu_sz"] == GraphiteEvent(
            path="stats.ol.ol-solr0.iostat.disk.vda.aqu_sz",
            value=1.64,
            timestamp=1713859200,
        )
        assert event_map["stats.ol.ol-solr0.iostat.avg_cpu.user"] == GraphiteEvent(
            path="stats.ol.ol-solr0.iostat.avg_cpu.user",
            value=58.8,
            timestamp=1713859200,
        )
