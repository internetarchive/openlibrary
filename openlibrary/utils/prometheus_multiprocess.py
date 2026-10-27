"""Prometheus metrics shared by a server's gunicorn workers.

In multiprocess mode prometheus_client keeps each worker's metrics in its own
``<type>_<pid>.db`` file in ``PROMETHEUS_MULTIPROC_DIR``, and ``/metrics`` adds them up.
When gunicorn recycles a worker, ``merge_dead_worker`` folds its counters, histograms
and summaries into ``<type>_archive.db`` and deletes its files, so the totals don't drop.

A scrape reads the files one at a time, so it must not overlap a merge: it could find a
file already deleted (a 500), or count a worker both in its file and in the archive (a
total that then drops, which Prometheus takes for a counter reset). So scrapes share a
lock that merges take exclusively.

Imported by gunicorn's master process (``docker/gunicorn_prometheus_conf.py``), so keep it light.
"""

from __future__ import annotations

import contextlib
import fcntl
import glob
import os
from typing import TYPE_CHECKING

from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, CollectorRegistry, generate_latest
from prometheus_client.mmap_dict import MmapedDict
from prometheus_client.multiprocess import MultiProcessCollector
from starlette.responses import Response

if TYPE_CHECKING:
    from collections.abc import Iterator

    from fastapi import FastAPI

LOCK_FILE = ".merge.lock"  # not a .db, so the collector doesn't read it
# Gauges aren't additive, so a dead worker's gauge values can't be merged into an archive
_ADDITIVE_TYPES = ("counter", "histogram", "summary")


@contextlib.contextmanager
def _locked(metrics_dir: str, operation: int) -> Iterator[None]:
    with open(os.path.join(metrics_dir, LOCK_FILE), "a") as lock_file:
        fcntl.flock(lock_file, operation)
        yield  # closing the file releases the lock


def merge_dead_worker(metrics_dir: str, pid: int) -> None:
    """Merge the additive metric files of the exited worker ``pid`` into the archives, and delete them."""
    with _locked(metrics_dir, fcntl.LOCK_EX):
        # prometheus_client doesn't expose a public merge API, so this relies on its file names and MmapedDict.
        # The tests in openlibrary/utils/tests/test_prometheus_multiprocess.py check both.
        for dead_file in glob.glob(os.path.join(metrics_dir, f"*_{pid}.db")):
            metric_type = os.path.basename(dead_file).split("_", maxsplit=1)[0]
            if metric_type not in _ADDITIVE_TYPES:
                continue

            archive = MmapedDict(os.path.join(metrics_dir, f"{metric_type}_archive.db"))
            try:
                for key, value, *_ in MmapedDict.read_all_values_from_file(dead_file):
                    archive.write_value(key, archive.read_value(key)[0] + value, 0)
            finally:
                archive.close()

            os.remove(dead_file)


_waiting: list[tuple[str, int]] = []
_merging = False


def on_worker_exit(metrics_dir: str, pid: int) -> None:
    """Gunicorn's ``child_exit`` hook: merge the exited worker ``pid``.

    Gunicorn calls it from its SIGCHLD handler, so another worker exiting can interrupt a merge with another call.
    That call only queues its worker, which the interrupted call merges next: merging right away would wait forever
    for the lock the interrupted merge holds. A worker queued just as the loop ends waits for the next worker to
    exit; until then scrapes still read its files.
    """
    global _merging
    _waiting.append((metrics_dir, pid))
    if _merging:
        return
    _merging = True
    try:
        while _waiting:
            merge_dead_worker(*_waiting.pop(0))
    finally:
        _merging = False


class LockedMultiProcessCollector(MultiProcessCollector):
    """``MultiProcessCollector`` that doesn't read the files while ``merge_dead_worker`` is changing them."""

    def __init__(self, registry: CollectorRegistry | None, path: str | None = None) -> None:
        super().__init__(registry, path)
        self._metrics_dir = path or os.environ["PROMETHEUS_MULTIPROC_DIR"]

    def collect(self):
        with _locked(self._metrics_dir, fcntl.LOCK_SH):
            return super().collect()


def metrics_registry() -> CollectorRegistry:
    """The registry to serve at ``/metrics``: all the workers' metrics in multiprocess mode, else this process's."""
    if "PROMETHEUS_MULTIPROC_DIR" not in os.environ:
        return REGISTRY
    registry = CollectorRegistry()
    LockedMultiProcessCollector(registry)
    return registry


def expose(app: FastAPI) -> None:
    """Serve the metrics at ``/metrics``. Use instead of ``Instrumentator.expose``, whose collector doesn't take the lock."""
    registry = metrics_registry()

    @app.get("/metrics", include_in_schema=False)
    def metrics() -> Response:
        return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)
