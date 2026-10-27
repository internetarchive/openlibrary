import fcntl
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, values
from prometheus_client.mmap_dict import MmapedDict

from openlibrary.utils import prometheus_multiprocess
from openlibrary.utils.prometheus_multiprocess import LockedMultiProcessCollector, merge_dead_worker, merge_dead_workers, worker_exited

GUNICORN_CONF = Path(__file__).parents[3] / "docker" / "gunicorn_prometheus_conf.py"


@pytest.fixture
def metrics_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMETHEUS_MULTIPROC_DIR", str(tmp_path))
    monkeypatch.setattr(prometheus_multiprocess, "_dead_workers", [])
    return tmp_path


def record_worker(monkeypatch, pid, requests):
    """Record ``requests`` requests the way gunicorn worker ``pid`` would, in its own ``<type>_<pid>.db`` files."""
    monkeypatch.setattr(values, "ValueClass", values.MultiProcessValue(lambda: pid))
    hits = Counter("hits", "Requests", registry=None)
    latency = Histogram("latency", "Latency", buckets=(1,), registry=None)
    hits.inc(requests)
    for _ in range(requests):
        latency.observe(0.5)


def totals(metrics_dir):
    registry = CollectorRegistry()
    LockedMultiProcessCollector(registry, str(metrics_dir))
    return registry.get_sample_value("hits_total"), registry.get_sample_value("latency_count")


def test_merge_dead_worker_keeps_totals(metrics_dir, monkeypatch):
    record_worker(monkeypatch, pid=1, requests=2)
    record_worker(monkeypatch, pid=2, requests=3)
    assert totals(metrics_dir) == (5, 5)

    assert merge_dead_worker(str(metrics_dir), 1)
    assert totals(metrics_dir) == (5, 5)
    assert not list(metrics_dir.glob("*_1.db"))
    assert (metrics_dir / "counter_archive.db").exists()
    assert (metrics_dir / "histogram_archive.db").exists()

    # Later workers add to the archive rather than replacing it
    record_worker(monkeypatch, pid=3, requests=4)
    merge_dead_worker(str(metrics_dir), 3)
    merge_dead_worker(str(metrics_dir), 2)
    assert totals(metrics_dir) == (9, 9)
    assert sorted(path.name for path in metrics_dir.glob("*.db")) == ["counter_archive.db", "histogram_archive.db"]


def test_merge_dead_worker_leaves_gauges(metrics_dir, monkeypatch):
    monkeypatch.setattr(values, "ValueClass", values.MultiProcessValue(lambda: 1))
    Gauge("in_progress", "In progress", multiprocess_mode="all", registry=None).set(1)

    merge_dead_worker(str(metrics_dir), 1)
    assert (metrics_dir / "gauge_all_1.db").exists()
    assert not (metrics_dir / "gauge_archive.db").exists()


def test_merge_during_scrape_waits(metrics_dir, monkeypatch):
    record_worker(monkeypatch, pid=1, requests=2)
    record_worker(monkeypatch, pid=2, requests=3)

    # Try to merge worker 1 while the scrape is between reading one file and the next. Unlocked, the merge would
    # delete a file the scrape is about to read, or add worker 1 to an archive after the scrape read its file.
    read_all_values_from_file = MmapedDict.read_all_values_from_file
    merged = []

    def read_while_merging(filename):
        if not merged:
            merged.append(merge_dead_worker(str(metrics_dir), 1))
        return read_all_values_from_file(filename)

    monkeypatch.setattr(MmapedDict, "read_all_values_from_file", staticmethod(read_while_merging))
    assert totals(metrics_dir) == (5, 5)
    assert merged == [False]  # it didn't wait for the scrape, and changed nothing
    assert (metrics_dir / "counter_1.db").exists()

    monkeypatch.undo()
    assert merge_dead_worker(str(metrics_dir), 1)
    assert totals(metrics_dir) == (5, 5)


def test_merge_dead_workers_tries_again_after_scrape(metrics_dir, monkeypatch):
    for pid in (1, 2, 3):
        record_worker(monkeypatch, pid=pid, requests=pid)
    worker_exited(1)
    worker_exited(2)

    with prometheus_multiprocess._locked(str(metrics_dir), fcntl.LOCK_SH):  # a scrape
        merge_dead_workers(str(metrics_dir))
    assert prometheus_multiprocess._dead_workers == [1, 2]
    assert len(list(metrics_dir.glob("counter_[0-9]*.db"))) == 3

    merge_dead_workers(str(metrics_dir))
    assert prometheus_multiprocess._dead_workers == []
    assert sorted(path.name for path in metrics_dir.glob("counter_*.db")) == ["counter_3.db", "counter_archive.db"]
    assert totals(metrics_dir) == (6, 6)


def test_merge_dead_workers_skips_reused_pid(metrics_dir, monkeypatch):
    record_worker(monkeypatch, pid=1, requests=2)
    worker_exited(1)

    # A new worker got pid 1 before the merge, so the files are its now
    merge_dead_workers(str(metrics_dir), live_pids={1})
    assert prometheus_multiprocess._dead_workers == []
    assert (metrics_dir / "counter_1.db").exists()
    assert totals(metrics_dir) == (2, 2)


def test_merge_dead_workers_drops_failing_worker(metrics_dir, monkeypatch):
    record_worker(monkeypatch, pid=2, requests=3)
    worker_exited(1)
    worker_exited(2)
    merge = Mock(side_effect=[RuntimeError("corrupt"), True])
    monkeypatch.setattr(prometheus_multiprocess, "merge_dead_worker", merge)

    with pytest.raises(RuntimeError):
        merge_dead_workers(str(metrics_dir))
    assert prometheus_multiprocess._dead_workers == [2]  # not tried again before every fork
    merge_dead_workers(str(metrics_dir))
    assert prometheus_multiprocess._dead_workers == []


def load_gunicorn_conf():
    spec = importlib.util.spec_from_file_location("gunicorn_prometheus_conf", GUNICORN_CONF)
    conf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(conf)
    return conf


def test_gunicorn_hooks_merge_exited_workers(metrics_dir, monkeypatch):
    conf = load_gunicorn_conf()
    record_worker(monkeypatch, pid=1, requests=2)
    server = SimpleNamespace(WORKERS={2: None}, log=Mock())

    conf.child_exit(server, SimpleNamespace(pid=1))
    assert (metrics_dir / "counter_1.db").exists()  # only queued, in the SIGCHLD handler
    conf.pre_fork(server, None)
    assert not (metrics_dir / "counter_1.db").exists()
    assert totals(metrics_dir) == (2, 2)
    server.log.exception.assert_not_called()


def test_gunicorn_pre_fork_logs_errors(metrics_dir, monkeypatch):
    # An exception in a hook would stop the gunicorn master
    conf = load_gunicorn_conf()
    monkeypatch.setattr(prometheus_multiprocess, "merge_dead_workers", Mock(side_effect=RuntimeError("corrupt")))
    server = SimpleNamespace(WORKERS={}, log=Mock())

    conf.pre_fork(server, None)
    server.log.exception.assert_called_once()
