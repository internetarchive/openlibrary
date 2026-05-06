import datetime
import unittest
from unittest.mock import patch

from scripts.solr_updater import trending_updater_init


class TestTrendingUpdaterInit:
    def _run_main(self, fake_now, main_kwargs):
        calls = []

        def fake_daily(timestamp, dry_run):
            calls.append(("daily", timestamp))

        def fake_hourly(timestamp, dry_run):
            calls.append(("hourly", timestamp))

        class PatchedDateTime(datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                return fake_now.replace(tzinfo=tz) if tz else fake_now

        with (
            patch(
                "scripts.solr_updater.trending_updater_init.run_daily_update",
                side_effect=fake_daily,
            ),
            patch(
                "scripts.solr_updater.trending_updater_init.run_hourly_update",
                side_effect=fake_hourly,
            ),
            patch(
                "scripts.solr_updater.trending_updater_init.datetime.datetime",
                PatchedDateTime,
            ),
        ):
            trending_updater_init.main("conf/openlibrary.yml", **main_kwargs)

        return calls

    def test_main_calls_hourly_and_daily_correctly(self):
        fake_now = datetime.datetime(2025, 6, 27, 3, 0, 0)
        start = datetime.datetime(2025, 6, 26, 0, 5, 0)
        actual_calls = self._run_main(
            fake_now,
            {
                "timestamp": start.isoformat(),
                "dry_run": True,
                "allow_old_timestamp": True,
            },
        )
        # There should be 27 hourly events (from 2025-06-26 00:05 to 2025-06-27 02:05) and 2 daily events (at 2025-06-26 and 2025-06-27)
        num_hourly = sum(1 for call in actual_calls if call[0] == "hourly")
        num_daily = sum(1 for call in actual_calls if call[0] == "daily")
        assert num_hourly == 27
        assert num_daily == 2

    def test_main_default_7_days(self):
        fake_now = datetime.datetime(2025, 6, 27, 0, 0, 0)
        actual_calls = self._run_main(fake_now, {"dry_run": True})
        # There should be 168 hourly events (7 days * 24 hours) and 7 daily events
        num_hourly = sum(1 for call in actual_calls if call[0] == "hourly")
        num_daily = sum(1 for call in actual_calls if call[0] == "daily")
        assert num_hourly == 168
        assert num_daily == 7

    def test_main_less_than_one_hour(self):
        fake_now = datetime.datetime(2025, 6, 27, 3, 0, 0)
        # Start is 2025-06-27 02:30:00, less than an hour before fake_now
        start = datetime.datetime(2025, 6, 27, 2, 30, 0)
        actual_calls = self._run_main(
            fake_now,
            {
                "timestamp": start.isoformat(),
                "dry_run": True,
                "allow_old_timestamp": True,
            },
        )

        expected_calls = [("hourly", datetime.datetime(2025, 6, 27, 2, 5, 0).isoformat())]
        assert actual_calls == expected_calls

    def test_main_three_hours(self):
        fake_now = datetime.datetime(2025, 6, 27, 3, 0, 0)
        start = datetime.datetime(2025, 6, 27, 0, 30, 0)

        actual_calls = self._run_main(
            fake_now,
            {
                "timestamp": start.isoformat(),
                "dry_run": True,
                "allow_old_timestamp": True,
            },
        )
        expected_calls = [
            ("daily", datetime.datetime(2025, 6, 27, 0, 0, 0).isoformat()),
            ("hourly", datetime.datetime(2025, 6, 27, 0, 5, 0).isoformat()),
            ("hourly", datetime.datetime(2025, 6, 27, 1, 5, 0).isoformat()),
            ("hourly", datetime.datetime(2025, 6, 27, 2, 5, 0).isoformat()),
        ]
        assert actual_calls == expected_calls


if __name__ == "__main__":
    unittest.main()
