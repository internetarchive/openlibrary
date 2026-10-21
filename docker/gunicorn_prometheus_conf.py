"""Gunicorn hooks for Prometheus multiprocess metrics."""

import glob
import os

from prometheus_client.mmap_dict import MmapedDict


def child_exit(server, worker):
    """Merge a worker's additive metric files into archives on exit."""
    metrics_dir = os.environ.get("PROMETHEUS_MULTIPROC_DIR")
    if not metrics_dir:
        return

    # prometheus_client doesn't expose a public merge API. The integration test
    # exercises these file names and MmapedDict methods across worker recycling.
    for dead_file in glob.glob(os.path.join(metrics_dir, f"*_{worker.pid}.db")):
        metric_type = os.path.basename(dead_file).split("_", maxsplit=1)[0]
        # Counters, histograms, and summaries store additive values. Gauges do
        # not, so their dead-worker values cannot be merged into an archive.
        if metric_type not in {"counter", "histogram", "summary"}:
            continue

        archive_path = os.path.join(metrics_dir, f"{metric_type}_archive.db")
        archive = MmapedDict(archive_path)
        try:
            for key, value, *_ in MmapedDict.read_all_values_from_file(dead_file):
                archive.write_value(key, archive.read_value(key)[0] + value, 0)
        finally:
            archive.close()

        os.remove(dead_file)
