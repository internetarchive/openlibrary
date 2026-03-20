#!/usr/bin/env python
"""
Monitor OpenLibrary worker processes and log them to a CSV file.

Matches processes whose command line contains one of the substrings in
WORKER_TYPES, tagging each match with the corresponding WorkerType label.

Runs every INTERVAL_SECONDS, appending one row per worker to a CSV:
  Time, PID, WorkerType, WorkerId, StartTime, TimeAlive

WorkerId assignment rules
--------------------------
- WorkerIds are assigned independently per WorkerType.
- First run (no persisted state): workers of each type are sorted by
  StartTime ascending and assigned IDs 1..N (per type).
- Subsequent runs: known PIDs keep their IDs.  IDs freed by exited workers
  are recycled (lowest freed ID first) before new IDs are minted.
- N per type is allowed to grow or shrink between runs.
"""

import contextlib
import csv
import dataclasses
import json
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

import psutil

from scripts.monitoring.utils import assign_stable_ids

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).parent
STATE_FILE = Path(tempfile.gettempdir()) / "monitor_workers_state.json"
CSV_FILE = SCRIPT_DIR / "monitor_workers.csv"

# Maps command-line substring → WorkerType label.
# A process is matched by the first key whose substring appears in its cmdline.
WORKER_TYPES: dict[str, str] = {
    "openlibrary-server": "webpy",
    "UvicornWorker": "fastapi",
}

INTERVAL_SECONDS = 60

CSV_COLUMNS = ["Time", "PID", "WorkerType", "WorkerId", "StartTime", "TimeAlive"]


@dataclasses.dataclass
class WorkerInfo:
    pid: int
    worker_type: str
    worker_id: int
    create_time: float  # Unix epoch from psutil


# ---------------------------------------------------------------------------
# Process discovery
# ---------------------------------------------------------------------------


def find_worker_processes() -> list[tuple[psutil.Process, str]]:
    """Return (process, worker_type) for every live matching process."""
    workers: list[tuple[psutil.Process, str]] = []
    for proc in psutil.process_iter(["pid", "cmdline", "create_time"]):
        try:
            cmdline = " ".join(proc.info["cmdline"] or [])
            for pattern, worker_type in WORKER_TYPES.items():
                if pattern in cmdline:
                    workers.append((proc, worker_type))
                    break  # first match wins
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return workers


# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------

# State type: {worker_type: {pid: worker_id}}
State = dict[str, dict[int, int]]


def load_state() -> State:
    """Return persisted {worker_type: {pid: worker_id}} mapping, or {} if none exists."""
    if STATE_FILE.exists():
        try:
            raw = json.loads(STATE_FILE.read_text())
            # Guard against old flat {pid: worker_id} format — values must be dicts.
            if any(not isinstance(v, dict) for v in raw.values()):
                return {}
            return {
                wtype: {int(pid): int(wid) for pid, wid in pids.items()}
                for wtype, pids in raw.items()
            }
        except (json.JSONDecodeError, ValueError, KeyError):
            pass
    return {}


def save_state(state: State) -> None:
    """Persist {worker_type: {pid: worker_id}} mapping to disk."""
    STATE_FILE.write_text(
        json.dumps(
            {
                wtype: {str(pid): wid for pid, wid in pids.items()}
                for wtype, pids in state.items()
            },
            indent=2,
        )
    )


# ---------------------------------------------------------------------------
# CSV output
# ---------------------------------------------------------------------------


def ensure_csv_header() -> None:
    """Write the CSV header if the file does not yet exist."""
    if not CSV_FILE.exists():
        with CSV_FILE.open("w", newline="") as fh:
            csv.DictWriter(fh, fieldnames=CSV_COLUMNS).writeheader()


def format_duration(total_seconds: float) -> str:
    """Format a duration as HH:MM:SS."""
    s = int(total_seconds)
    h, remainder = divmod(s, 3600)
    m, sec = divmod(remainder, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}"


def write_csv_rows(workers: list[WorkerInfo]) -> None:
    """Append one row per worker to the CSV file."""
    now = datetime.now(UTC)
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")

    with CSV_FILE.open("a", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        for w in sorted(workers, key=lambda w: (w.worker_type, w.worker_id)):
            start_dt = datetime.fromtimestamp(w.create_time, tz=UTC)
            writer.writerow(
                {
                    "Time": now_str,
                    "PID": w.pid,
                    "WorkerType": w.worker_type,
                    "WorkerId": w.worker_id,
                    "StartTime": start_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "TimeAlive": format_duration(now.timestamp() - w.create_time),
                }
            )


# ---------------------------------------------------------------------------
# Core function
# ---------------------------------------------------------------------------


def get_worker_metrics() -> list[WorkerInfo]:
    """Discover live workers, assign IDs, persist state, return WorkerInfo list."""
    state = load_state()

    workers = find_worker_processes()
    if not workers:
        return []

    # Sorting by create time so older processes get lower IDs
    workers = sorted(workers, key=lambda w: w[0].create_time())

    by_type: dict[str, list[psutil.Process]] = {}
    for proc, wtype in workers:
        by_type.setdefault(wtype, []).append(proc)
    state = {
        wtype: assign_stable_ids([p.pid for p in procs], state.get(wtype, {}))
        for wtype, procs in by_type.items()
    }
    save_state(state)

    snapshots = []
    for proc, wtype in workers:
        worker_id = state.get(wtype, {}).get(proc.pid)
        if worker_id is None:
            continue
        with contextlib.suppress(psutil.NoSuchProcess, psutil.AccessDenied):
            snapshots.append(
                WorkerInfo(
                    pid=proc.pid,
                    worker_type=wtype,
                    worker_id=worker_id,
                    create_time=proc.create_time(),
                )
            )
    return snapshots


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


def run_once() -> None:
    """Execute a single monitoring pass."""
    ts = datetime.now().strftime("%H:%M:%S")
    snapshots = get_worker_metrics()

    if not snapshots:
        print(f"[{ts}] No matching worker processes found.")
        return

    ensure_csv_header()
    write_csv_rows(snapshots)

    by_type: dict[str, int] = {}
    for w in snapshots:
        by_type[w.worker_type] = by_type.get(w.worker_type, 0) + 1
    summary = ", ".join(f"{t}={n}" for t, n in sorted(by_type.items()))
    print(f"[{ts}] Logged {len(snapshots)} worker(s): {summary}")


def main() -> None:
    print("Worker monitor started.")
    for pattern, wtype in WORKER_TYPES.items():
        print(f"  Matching:  '{pattern}' → {wtype}")
    print(f"  CSV:       {CSV_FILE}")
    print(f"  State:     {STATE_FILE}")
    print(f"  Interval:  {INTERVAL_SECONDS}s")
    print("Press Ctrl+C to stop.\n")

    try:
        while True:
            run_once()
            time.sleep(INTERVAL_SECONDS)
    except KeyboardInterrupt:
        print("\nMonitor stopped.")


if __name__ == "__main__":
    main()
