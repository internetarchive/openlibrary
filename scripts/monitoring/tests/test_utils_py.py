from unittest.mock import patch

from scripts.monitoring.utils import bash_run, limit_server
from scripts.utils.scheduler import OlAsyncIOScheduler


def test_bash_run():
    with patch("subprocess.run") as mock_subprocess_run:
        # Test without sources
        bash_run("echo 'Hello, World!'")
        assert mock_subprocess_run.call_args[0][0] == [
            "bash",
            "-c",
            "set -e\necho 'Hello, World!'",
        ]

        # Test with sources
        mock_subprocess_run.reset_mock()
        bash_run("echo 'Hello, World!'", sources=["source1.sh", "source2.sh"])
        assert mock_subprocess_run.call_args[0][0] == [
            "bash",
            "-c",
            'set -e\nsource "scripts/monitoring/source1.sh"\nsource "scripts/monitoring/source2.sh"\necho \'Hello, World!\'',
        ]


def test_limit_server():
    with patch("os.environ.get", return_value="allowed-server"):
        scheduler = OlAsyncIOScheduler("X")

        @limit_server(["allowed-server"], scheduler)
        @scheduler.scheduled_job("interval", seconds=60)
        def sample_job():
            pass

        sample_job()
        assert scheduler.get_job("sample_job") is not None

    with patch("os.environ.get", return_value="other-server"):
        scheduler = OlAsyncIOScheduler("X")

        @limit_server(["allowed-server"], scheduler)
        @scheduler.scheduled_job("interval", seconds=60)
        def sample_job():
            pass

        sample_job()
        assert scheduler.get_job("sample_job") is None

    with patch("os.environ.get", return_value="allowed-server0"):
        scheduler = OlAsyncIOScheduler("X")

        @limit_server(["allowed-server*"], scheduler)
        @scheduler.scheduled_job("interval", seconds=60)
        def sample_job():
            pass

        sample_job()
        assert scheduler.get_job("sample_job") is not None

    with patch("os.environ.get", return_value="ol-web0.us.archive.org"):
        scheduler = OlAsyncIOScheduler("X")

        @limit_server(["ol-web0"], scheduler)
        @scheduler.scheduled_job("interval", seconds=60)
        def sample_job():
            pass

        sample_job()
        assert scheduler.get_job("sample_job") is not None
