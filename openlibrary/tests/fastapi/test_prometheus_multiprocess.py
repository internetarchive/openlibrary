import importlib.metadata
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

_REAL_SLEEP = time.sleep


def run_reproduction(mode, workdir, successful_requests):
    """Run the issue's Gunicorn/Instrumentator reproduction in bug or fixed mode."""
    if mode not in {"bug", "fixed"}:
        raise ValueError("mode must be 'bug' or 'fixed'")

    workdir = Path(workdir)
    app_path = workdir / "app.py"
    app_path.write_text(
        """from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI()

@app.get('/hit')
def hit():
    return {'ok': True}

Instrumentator(
    should_group_status_codes=False,
    excluded_handlers=['/health', '/metrics'],
).instrument(app).expose(app, include_in_schema=False)
"""
    )

    metrics_dir = workdir / "metrics"
    metrics_dir.mkdir()
    environment = os.environ.copy()
    environment.pop("PROMETHEUS_MULTIPROC_DIR", None)
    command = [
        sys.executable,
        "-m",
        "gunicorn",
        "-k",
        "uvicorn.workers.UvicornWorker",
        "--workers",
        "4",
        "--max-requests",
        "60",
        "--max-requests-jitter",
        "0",
    ]
    if mode == "fixed":
        repo_root = Path.cwd()
        if not (repo_root / "docker" / "gunicorn_prometheus_conf.py").is_file():
            repo_root = Path(__file__).resolve().parents[3]
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

    def request(path):
        with urllib.request.urlopen(base_url + path, timeout=10) as response:
            return response.read().decode()

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

        def hit(_):
            for attempt in range(30):
                try:
                    request("/hit")
                    return
                except urllib.error.URLError, ConnectionError, TimeoutError:
                    if attempt == 29:
                        raise
                    time.sleep(0.05)

        with ThreadPoolExecutor(max_workers=10) as executor:
            list(executor.map(hit, range(successful_requests)))

        samples = []
        for _ in range(5):
            metrics = request("/metrics")
            values = [
                float(line.rsplit(" ", maxsplit=1)[1]) for line in metrics.splitlines() if line.startswith("http_requests_total{") and 'handler="/hit"' in line
            ]
            samples.append(sum(values))
        return samples, metrics_dir
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
    samples, metrics_dir = run_reproduction("fixed", tmp_path, successful_requests=1000)

    assert samples == [1000.0] * 5
    for metric_type in ("counter", "histogram", "summary"):
        assert (metrics_dir / f"{metric_type}_archive.db").exists()
        assert len(list(metrics_dir.glob(f"{metric_type}_[0-9]*.db"))) <= 4


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "bug"
    with tempfile.TemporaryDirectory(prefix="metrics-repro-") as workdir:
        successful_requests = 300
        samples, _ = run_reproduction(mode, workdir, successful_requests)
        version = importlib.metadata.version("prometheus-fastapi-instrumentator")
        print(f"mode={mode}, instrumentator={version}, successful_requests={successful_requests}")
        print(f"http_requests_total samples: {samples}")
