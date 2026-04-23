import json
from unittest.mock import MagicMock, patch

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


def test_get_iostat_payload_runs_expected_command():
    mock_result = MagicMock()
    mock_result.stdout = FAKE_IOSTAT_JSON

    with patch("scripts.monitoring.iostat_monitor.bash_run", return_value=mock_result) as mock_bash_run:
        payload = get_iostat_payload()

    mock_bash_run.assert_called_once_with(IOSTAT_COMMAND, capture_output=True)
    assert payload["sysstat"]["hosts"]


def test_get_iostat_events_generates_disk_and_cpu_events():
    with patch("scripts.monitoring.iostat_monitor.get_iostat_payload", return_value=json.loads(FAKE_IOSTAT_JSON)):
        events = get_iostat_events(bucket="stats.ol.ol-solr0", timestamp=1713859200)

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
