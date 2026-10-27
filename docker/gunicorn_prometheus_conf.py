"""Gunicorn hooks for Prometheus multiprocess metrics."""

import os


def child_exit(server, worker):
    """Merge a worker's additive metric files into archives on exit."""
    # Imported here, as pytest's --doctest-modules imports this file without the repo on sys.path
    from openlibrary.utils.prometheus_multiprocess import on_worker_exit  # noqa: PLC0415

    if metrics_dir := os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        on_worker_exit(metrics_dir, worker.pid)
