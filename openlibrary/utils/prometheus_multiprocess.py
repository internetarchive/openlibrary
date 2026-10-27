"""Prometheus metrics shared by a server's gunicorn workers.

In multiprocess mode prometheus_client keeps each worker's metrics in its own
``<type>_<pid>.db`` file in ``PROMETHEUS_MULTIPROC_DIR``, and ``/metrics`` adds them up.
When gunicorn recycles a worker, ``merge_dead_worker`` folds its counters, histograms
and summaries into ``<type>_archive.db`` and deletes its files, so the totals don't drop.

A scrape reads the files one at a time, so it must not overlap a merge: it could find a
file already deleted (a 500), or count a worker both in its file and in the archive (a
total that then drops, which Prometheus takes for a counter reset). So scrapes share a
lock that merges take exclusively.

The merges run in gunicorn's master, which mustn't wait on scrapes: they can take seconds,
and a steady stream of them would hold the lock indefinitely. So the master only merges when
no scrape is running, and otherwise tries again before it next starts a worker. Until then,
scrapes still read the dead worker's files, so the totals stay right.

Imported by gunicorn's master process (``docker/gunicorn_prometheus_conf.py``), so keep it light.
"""

from __future__ import annotations

import contextlib
import fcntl
import glob
import os
import shutil
from typing import TYPE_CHECKING

from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, CollectorRegistry, generate_latest
from prometheus_client.mmap_dict import MmapedDict
from prometheus_client.multiprocess import MultiProcessCollector
from starlette.responses import Response

if TYPE_CHECKING:
    from collections.abc import Container, Iterator

    from fastapi import FastAPI

LOCK_FILE = ".merge.lock"  # not a .db, so the collector doesn't read it
# Gauges aren't additive, so a dead worker's gauge values can't be merged into an archive
_ADDITIVE_TYPES = ("counter", "histogram", "summary")


@contextlib.contextmanager
def _locked(metrics_dir: str, operation: int) -> Iterator[bool]:
    """Hold the lock for the block. With ``LOCK_NB``, yields False instead of waiting for it."""
    with open(os.path.join(metrics_dir, LOCK_FILE), "a") as lock_file:
        try:
            fcntl.flock(lock_file, operation)
        except BlockingIOError:
            yield False
            return
        yield True  # closing the file releases the lock


def merge_dead_worker(metrics_dir: str, pid: int) -> bool:
    """Merge the additive metric files of the exited worker ``pid`` into the archives, and delete them.

    Returns False, merging nothing, if a scrape is reading the files.
    """
    with _locked(metrics_dir, fcntl.LOCK_EX | fcntl.LOCK_NB) as locked:
        if not locked:
            return False
        # prometheus_client doesn't expose a public merge API, so this relies on its file names and MmapedDict.
        # The tests in openlibrary/utils/tests/test_prometheus_multiprocess.py check both.
        for dead_file in glob.glob(os.path.join(metrics_dir, f"*_{pid}.db")):
            metric_type = os.path.basename(dead_file).split("_", maxsplit=1)[0]
            if metric_type not in _ADDITIVE_TYPES:
                continue

            if not os.path.getsize(dead_file):  # the worker exited before sizing it, so it has no values
                os.remove(dead_file)
                continue

            # Failing halfway must change neither file, or scrapes would count the values already merged again from
            # the dead file. So read the dead file before writing anything (it may be corrupt), merge into a copy of
            # the archive (writing may fail, e.g. on a full disk), and replace the archive with it. Only failing to
            # remove the dead file after that would count it twice, until the start scripts clear the directory.
            dead_values = list(MmapedDict.read_all_values_from_file(dead_file))
            archive_path = os.path.join(metrics_dir, f"{metric_type}_archive.db")
            new_archive_path = f"{archive_path}.new"  # not a .db, so the collector doesn't read it
            with contextlib.suppress(FileNotFoundError):
                os.remove(new_archive_path)  # left by a merge that failed
            if os.path.exists(archive_path):
                shutil.copyfile(archive_path, new_archive_path)

            new_archive = MmapedDict(new_archive_path)
            try:
                for key, value, *_ in dead_values:
                    new_archive.write_value(key, new_archive.read_value(key)[0] + value, 0)
            finally:
                new_archive.close()

            os.replace(new_archive_path, archive_path)
            os.remove(dead_file)
    return True


# Exited workers, oldest first, not yet merged
_dead_workers: list[int] = []


def worker_exited(pid: int) -> None:
    """Queue the exited worker ``pid`` for ``merge_dead_workers``.

    For gunicorn's ``child_exit`` hook, which it calls from its SIGCHLD handler, so this only appends: anything more
    could be interrupted by another worker exiting, or block the master.
    """
    _dead_workers.append(pid)


def merge_dead_workers(metrics_dir: str, live_pids: Container[int] = ()) -> int:
    """Merge the queued exited workers, stopping if a scrape is reading the files. For gunicorn's ``pre_fork`` hook.

    ``live_pids`` are the running workers: if one reused a queued worker's pid, those files are its now.
    Returns how many are still queued, to be tried again before the next fork.
    """
    while _dead_workers:
        pid = _dead_workers[0]
        try:
            if pid not in live_pids and not merge_dead_worker(metrics_dir, pid):
                return len(_dead_workers)
        except Exception:
            _dead_workers.pop(0)  # don't fail on the same files before every fork
            raise
        _dead_workers.pop(0)
    return 0


class LockedMultiProcessCollector(MultiProcessCollector):
    """``MultiProcessCollector`` that doesn't read the files while ``merge_dead_worker`` is changing them."""

    def __init__(self, registry: CollectorRegistry | None, path: str | None = None) -> None:
        super().__init__(registry, path)
        self._metrics_dir = path or os.environ["PROMETHEUS_MULTIPROC_DIR"]

    def collect(self):
        with _locked(self._metrics_dir, fcntl.LOCK_SH):
            # A new worker creates its files empty and then sizes them, and reading one in between fails. It has no
            # values yet, and a file never goes back to empty, so skip it.
            files = [path for path in glob.glob(os.path.join(self._metrics_dir, "*.db")) if _has_values(path)]
            return self.merge(files, accumulate=True)


def _has_values(path: str) -> bool:
    try:
        return os.path.getsize(path) > 0
    except FileNotFoundError:  # as the upstream collector allows, e.g. for live gauges' files of exited workers
        return False


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
