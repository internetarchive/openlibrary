"""Gunicorn hooks for Prometheus multiprocess metrics; see openlibrary/utils/prometheus_multiprocess.py.

An exception in a hook stops the gunicorn master, and with it every worker, so the hooks log errors instead.
"""

import os

from openlibrary.utils import prometheus_multiprocess


def child_exit(server, worker):
    """Queue the exited worker's metric files to be merged into the archives."""
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        prometheus_multiprocess.worker_exited(worker.pid)


def pre_fork(server, worker):
    """Merge the exited workers' metric files, from the master's main loop, before it starts a worker."""
    if metrics_dir := os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        try:
            prometheus_multiprocess.merge_dead_workers(metrics_dir, live_pids=server.WORKERS)
        except Exception:
            server.log.exception("Failed to merge the Prometheus metrics of exited workers")
