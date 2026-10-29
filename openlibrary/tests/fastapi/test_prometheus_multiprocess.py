import importlib.metadata
import os
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path

_REAL_SLEEP = time.sleep
WORKERS = 4
MAX_REQUESTS = 60


def _request(base_url, path):
    for attempt in range(30):
        try:
            with urllib.request.urlopen(base_url + path, timeout=2) as response:
                return response.read().decode()
        except urllib.error.HTTPError:
            raise
        except urllib.error.URLError, ConnectionError, TimeoutError:
            # A recycled Uvicorn worker closes the connections it accepted but hadn't read a request from yet
            if attempt == 29:
                raise
            time.sleep(0.05)


def _hits_total(base_url):
    lines = _request(base_url, "/metrics").splitlines()
    return sum(float(line.rsplit(" ", maxsplit=1)[1]) for line in lines if line.startswith("http_requests_total{") and 'handler="/hit"' in line)


def _scrape_until(stop, base_url, scrapes):
    """Scrape until ``stop`` is set, recording in ``scrapes`` the problem with each, or None."""
    last = 0.0
    while not stop.is_set():
        try:
            total = _hits_total(base_url)
        except Exception as error:  # noqa: BLE001 - any failure is the test's to report, not the thread's
            scrapes.append(repr(error))
        else:
            scrapes.append(f"total went from {last} to {total}" if total < last else None)
            last = max(last, total)
        time.sleep(0.01)


def run_reproduction(mode, workdir, successful_requests):
    """Run the issue's Gunicorn/Instrumentator reproduction in bug or fixed mode."""
    if mode not in {"bug", "fixed"}:
        raise ValueError("mode must be 'bug' or 'fixed'")

    workdir = Path(workdir)
    app_path = workdir / "app.py"
    app_path.write_text(
        """from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from openlibrary.utils import prometheus_multiprocess

app = FastAPI()

@app.get('/hit')
def hit():
    return {'ok': True}

Instrumentator(
    should_group_status_codes=False,
    excluded_handlers=['/health', '/metrics'],
).instrument(app)
prometheus_multiprocess.expose(app)
"""
    )

    metrics_dir = workdir / "metrics"
    metrics_dir.mkdir()
    environment = os.environ.copy()
    environment.pop("PROMETHEUS_MULTIPROC_DIR", None)
    repo_root = Path.cwd()
    if not (repo_root / "docker" / "gunicorn_prometheus_conf.py").is_file():
        repo_root = Path(__file__).resolve().parents[3]
    environment["PYTHONPATH"] = str(repo_root)  # for app.py and the gunicorn config to import openlibrary
    command = [
        sys.executable,
        "-m",
        "gunicorn",
        "-k",
        "uvicorn.workers.UvicornWorker",
        "--workers",
        str(WORKERS),
        "--max-requests",
        str(MAX_REQUESTS),
        "--max-requests-jitter",
        "0",
    ]
    if mode == "fixed":
        gunicorn_config = repo_root / "docker" / "gunicorn_prometheus_conf.py"
        if not gunicorn_config.is_file():
            raise RuntimeError(f"fixed mode requires {gunicorn_config}")
        environment["PROMETHEUS_MULTIPROC_DIR"] = str(metrics_dir)
        command.extend(["--config", str(gunicorn_config)])

    with socket.socket() as server_socket:
        server_socket.bind(("127.0.0.1", 0))
        port = server_socket.getsockname()[1]
    command.extend(["--bind", f"127.0.0.1:{port}", "app:app"])

    process = subprocess.Popen(
        command,
        cwd=workdir,
        env=environment,
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base_url = f"http://127.0.0.1:{port}"

    request = partial(_request, base_url)
    hits_total = partial(_hits_total, base_url)

    try:
        for _ in range(120):
            if process.poll() is not None:
                raise RuntimeError("Gunicorn exited before becoming ready")
            try:
                request("/metrics")
                break
            except urllib.error.URLError, TimeoutError:
                time.sleep(0.1)
        else:
            raise RuntimeError("Gunicorn did not become ready")

        # Scrape while workers recycle for the first half of the requests. Then stop, so the workers that exit in
        # the second half (more requests than --max-requests times the workers) merge those that waited for a scrape.
        scrapes = []
        stop_scraping = threading.Event()
        scraper = threading.Thread(target=_scrape_until, args=(stop_scraping, base_url, scrapes))
        scraped_requests = successful_requests // 2
        with ThreadPoolExecutor(max_workers=10) as executor:
            scraper.start()
            try:
                list(executor.map(lambda _: request("/hit"), range(scraped_requests)))
            finally:
                stop_scraping.set()
                scraper.join()
            list(executor.map(lambda _: request("/hit"), range(successful_requests - scraped_requests)))

        # The instrumentator counts a request just after sending its response, so the last ones can lag a little
        deadline = time.monotonic() + 10
        while hits_total() < successful_requests and time.monotonic() < deadline:
            time.sleep(0.1)
        samples = [hits_total() for _ in range(5)]

        # The master merges an exited worker as it starts the replacement, unless a scrape holds the lock (as the
        # ones above may have), when it waits for the next. So recycle a worker without scraping, which merges any
        # still waiting, and give the master a moment to replace the workers that exit.
        for _ in range(WORKERS * MAX_REQUESTS + 1):
            request("/hit")
        deadline = time.monotonic() + 5
        while len(list(metrics_dir.glob("counter_[0-9]*.db"))) > WORKERS and time.monotonic() < deadline:
            time.sleep(0.1)
        return samples, metrics_dir, scrapes
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()


def test_gunicorn_worker_recycling_preserves_prometheus_totals(tmp_path, monkeypatch):
    # The repository's autouse no_sleep fixture blocks sleeps, but this test
    # needs real timing while polling a separate Gunicorn process.
    monkeypatch.setattr(time, "sleep", _REAL_SLEEP)
    samples, metrics_dir, scrapes = run_reproduction("fixed", tmp_path, successful_requests=1000)

    assert scrapes  # while workers recycled
    assert [problem for problem in scrapes if problem] == []
    assert samples == [1000.0] * 5
    for metric_type in ("counter", "histogram", "summary"):
        assert (metrics_dir / f"{metric_type}_archive.db").exists()
        assert len(list(metrics_dir.glob(f"{metric_type}_[0-9]*.db"))) <= WORKERS


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "bug"
    with tempfile.TemporaryDirectory(prefix="metrics-repro-") as workdir:
        successful_requests = 300
        samples, _, scrapes = run_reproduction(mode, workdir, successful_requests)
        version = importlib.metadata.version("prometheus-fastapi-instrumentator")
        print(f"mode={mode}, instrumentator={version}, successful_requests={successful_requests}")
        print(f"http_requests_total samples: {samples}")
        problems = [problem for problem in scrapes if problem]
        print(f"scrapes while workers recycled: {len(scrapes)}, with problems: {len(problems)} {problems[:5]}")
