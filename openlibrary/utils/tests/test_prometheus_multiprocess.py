import threading

import pytest
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, values
from prometheus_client.mmap_dict import MmapedDict

from openlibrary.utils.prometheus_multiprocess import LockedMultiProcessCollector, merge_dead_worker, on_worker_exit


@pytest.fixture
def metrics_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMETHEUS_MULTIPROC_DIR", str(tmp_path))
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

    merge_dead_worker(str(metrics_dir), 1)
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


def test_scrape_waits_for_merge(metrics_dir, monkeypatch):
    record_worker(monkeypatch, pid=1, requests=2)
    record_worker(monkeypatch, pid=2, requests=3)

    # Try to merge worker 1 while the scrape is between reading one file and the next. Unlocked, the merge would
    # delete a file the scrape is about to read, or add worker 1 to an archive after the scrape read its file.
    merge = threading.Thread(target=merge_dead_worker, args=(str(metrics_dir), 1))
    read_all_values_from_file = MmapedDict.read_all_values_from_file

    def read_while_merging(filename):
        if not merge.ident:
            merge.start()
            merge.join(timeout=0.2)
        return read_all_values_from_file(filename)

    monkeypatch.setattr(MmapedDict, "read_all_values_from_file", staticmethod(read_while_merging))
    assert totals(metrics_dir) == (5, 5)

    merge.join(timeout=5)
    assert not merge.is_alive()
    assert not list(metrics_dir.glob("*_1.db"))
    assert totals(metrics_dir) == (5, 5)


def test_worker_exit_during_merge(metrics_dir, monkeypatch):
    record_worker(monkeypatch, pid=1, requests=2)
    record_worker(monkeypatch, pid=2, requests=3)

    # Gunicorn calls on_worker_exit from its SIGCHLD handler, so worker 2 exiting can interrupt worker 1's merge
    read_all_values_from_file = MmapedDict.read_all_values_from_file
    interrupted = []

    def read_and_interrupt(filename):
        if not interrupted:
            interrupted.append(filename)
            on_worker_exit(str(metrics_dir), 2)
        return read_all_values_from_file(filename)

    monkeypatch.setattr(MmapedDict, "read_all_values_from_file", staticmethod(read_and_interrupt))
    # In a thread, so a deadlock fails the test instead of hanging it
    merge = threading.Thread(target=on_worker_exit, args=(str(metrics_dir), 1), daemon=True)
    merge.start()
    merge.join(timeout=5)
    assert not merge.is_alive()

    assert interrupted
    assert sorted(path.name for path in metrics_dir.glob("*.db")) == ["counter_archive.db", "histogram_archive.db"]
    assert totals(metrics_dir) == (5, 5)
