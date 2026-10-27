"""Gunicorn hooks for Prometheus multiprocess metrics."""

import os

from openlibrary.utils.prometheus_multiprocess import on_worker_exit


def child_exit(server, worker):
    """Merge a worker's additive metric files into archives on exit."""
    if metrics_dir := os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        on_worker_exit(metrics_dir, worker.pid)
