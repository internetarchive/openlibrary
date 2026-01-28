import os
import re
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import ANY, patch

os.environ['HOSTNAME'] = 'ol-www0.us.archive.org'
from scripts.monitoring.haproxy_monitor import GraphiteEvent
from scripts.monitoring.monitor import monitor_partner_useragents


class TestMonitorPartnerUseragents:
    def test_monitor_partner_useragents(self):
        """Test monitor_partner_useragents with sample nginx logs."""
        with TemporaryDirectory() as tmpdir:
            # Copy logs to temporary directory
            sample_log_path = Path(__file__).parent / "sample_partners_nginx_logs.log"
            temp_log_path = Path(tmpdir) / "access.log"
            shutil.copy(sample_log_path, temp_log_path)

            # Update timestamps to current time
            now = datetime.now() - timedelta(minutes=1)
            make_logs_relative_to(temp_log_path, now=now)

            os.environ['OBFI_NEVER_DOCKER'] = 'true'
            os.environ['OBFI_SUDO'] = ''
            os.environ['OBFI_LOG_DIR'] = Path(tmpdir).as_posix()

            with patch.object(GraphiteEvent, 'submit_many') as mock_submit:
                monitor_partner_useragents()

                assert mock_submit.called, "GraphiteEvent.submit_many not called"
                events = mock_submit.call_args[0][0]
                assert events == [
                    GraphiteEvent(
                        path='stats.ol.partners.Whefi',
                        value=1.0,
                        timestamp=ANY,
                    ),
                    GraphiteEvent(
                        path='stats.ol.partners.Bookscovery',
                        value=1.0,
                        timestamp=ANY,
                    ),
                ]


def make_logs_relative_to(file: Path, now: datetime | None = None):
    """
    Update all timestamps in a log file so that the maximum timestamp becomes the current time.

    Args:
        file: Path to the log file to update
    """
    # Read the log file and find the largest timestamp
    with open(file) as f:
        log_content = f.read()

    # Parse timestamps from the log file (format: [28/Nov/2025:18:00:57 +0000])
    timestamp_pattern = r'\[(\d{2}/\w{3}/\d{4}:\d{2}:\d{2}:\d{2}) \+0000\]'
    timestamps = re.findall(timestamp_pattern, log_content)
    assert timestamps, "No timestamps found in the log file."

    # Convert timestamps to datetime objects
    max_timestamp = max(datetime.strptime(ts, '%d/%b/%Y:%H:%M:%S') for ts in timestamps)
    current_time = now or datetime.now()

    # Calculate the time difference in seconds
    time_diff = int((current_time - max_timestamp).total_seconds())

    # Update all timestamps in the log file
    def update_timestamp(match):
        original_ts = match.group(1)
        ts_datetime = datetime.strptime(original_ts, '%d/%b/%Y:%H:%M:%S')
        # Add the time difference to bring it to current time
        new_datetime = ts_datetime + timedelta(seconds=time_diff)
        new_ts = new_datetime.strftime('%d/%b/%Y:%H:%M:%S')
        return f'[{new_ts} +0000]'

    updated_content = re.sub(timestamp_pattern, update_timestamp, log_content)

    # Write the updated content back to the file
    with open(file, 'w') as f:
        f.write(updated_content)
