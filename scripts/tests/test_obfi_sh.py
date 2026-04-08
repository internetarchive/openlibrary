from datetime import datetime
from pathlib import Path

from scripts.monitoring.utils import bash_run

SAMPLE_LOG = Path("./scripts/tests/sample_nginx_access.log")
OBFI_SH = Path("./scripts/obfi.sh")


def iso_to_ms(iso_str):
    dt = datetime.fromisoformat(iso_str)
    return int(dt.timestamp() * 1000)


def bash_w_obfi(cmd: str):
    return bash_run(
        cmd,
        sources=[OBFI_SH.absolute()],
        capture_output=True,
    )


class TestObfiMatchRange:
    def test_obfi_match_range_multi_day(self):
        # All lines in the sample log are between 2025-06-27 00:28:46 and 2025-06-28 01:01:46
        start_iso = "2025-06-27T00:00:00Z"
        end_iso = "2025-06-28T23:59:59Z"
        start = iso_to_ms(start_iso)
        end = iso_to_ms(end_iso)
        output = bash_w_obfi(f"cat {SAMPLE_LOG} | obfi_match_range {start} {end}")
        assert output.stdout == SAMPLE_LOG.read_text()

    def test_obfi_match_range_first_hour(self):
        # Only lines on 2025-06-27 between 00:00:00 and 00:59:59 should match (first line only)
        start_iso = "2025-06-27T00:00:00Z"
        end_iso = "2025-06-27T00:59:59Z"
        start = iso_to_ms(start_iso)
        end = iso_to_ms(end_iso)
        output = bash_w_obfi(f"cat {SAMPLE_LOG} | obfi_match_range {start} {end}")
        expected = SAMPLE_LOG.read_text().splitlines()[0] + "\n"
        assert output.stdout == expected

    def test_obfi_match_range_second_day_same_hour(self):
        # Only lines on 2025-06-28 between 00:00:00 and 00:59:59 should match (third line only)
        start_iso = "2025-06-28T00:00:00Z"
        end_iso = "2025-06-28T00:59:59Z"
        start = iso_to_ms(start_iso)
        end = iso_to_ms(end_iso)
        output = bash_w_obfi(f"cat {SAMPLE_LOG} | obfi_match_range {start} {end}")
        expected = SAMPLE_LOG.read_text().splitlines()[2] + "\n"
        assert output.stdout == expected

    def test_obfi_match_range_no_lines(self):
        start_iso = "2001-09-09T01:46:40Z"
        end_iso = "2001-09-09T01:46:41Z"
        start = iso_to_ms(start_iso)
        end = iso_to_ms(end_iso)
        output = bash_w_obfi(f"cat {SAMPLE_LOG} | obfi_match_range {start} {end}")
        assert output.stdout == ""
