#!/usr/bin/env python3
"""
Monitor PostgreSQL connections and log them to a CSV file.

Runs a query against pg_stat_activity every INTERVAL_SECONDS and appends
one row per connection to a CSV:
  Time, PID, Hostname, ConnectionId, StartTime, TimeAlive, State

ConnectionId assignment rules
-------------------------------
- ConnectionIds are assigned independently per Hostname.
- First run (no persisted state): connections of each hostname are sorted by
  StartTime ascending and assigned IDs 1..N (per hostname).
- Subsequent runs: known PIDs keep their IDs.  IDs freed by closed connections
  are recycled (lowest freed ID first) before new IDs are minted.
- N per hostname is allowed to grow or shrink between runs.
"""

import contextlib
import csv
import dataclasses
import functools
import json
import os
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

import psycopg2
import yaml

from scripts.monitoring.utils import assign_stable_ids

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).parent
STATE_FILE = Path(tempfile.gettempdir()) / "monitor_db_connections_state.json"
CSV_FILE = SCRIPT_DIR / "monitor_db_connections.csv"


@functools.cache
def _load_db_params() -> dict:
    """Read DB connection params from OL_CONFIG → infobase_config_file → db_parameters.

    Returns a dict of kwargs ready to pass directly to psycopg2.connect().
    Result is cached so the files are only read once.
    """
    ol_config_path = os.environ.get("OL_CONFIG")
    if not ol_config_path:
        raise RuntimeError("OL_CONFIG environment variable is not set.")

    ol_config = yaml.safe_load(Path(ol_config_path).read_text())
    infobase_config_path = ol_config.get("infobase_config_file")
    if not infobase_config_path:
        raise RuntimeError("'infobase_config_file' not found in OL_CONFIG.")

    # Resolve relative paths against the directory containing OL_CONFIG.
    infobase_path = Path(ol_config_path).parent / infobase_config_path
    db = yaml.safe_load(infobase_path.read_text()).get("db_parameters", {})

    return {
        "host": db["host"],
        "user": db["username"],
        "dbname": db["database"],
        "password": db.get("password", ""),
    }


INTERVAL_SECONDS = 60

CSV_COLUMNS = [
    "Time",
    "PID",
    "Hostname",
    "ConnectionId",
    "StartTime",
    "TimeAlive",
    "State",
]

QUERY = """
SELECT
    pid,
    backend_start,
    COALESCE(state, '') AS state,
    extract(epoch FROM now() - backend_start) AS session_age_seconds,
    CASE client_addr
        WHEN '207.241.231.16'  THEN 'ol-web1'
        WHEN '207.241.231.169' THEN 'ol-dev1'
        WHEN '207.241.234.145' THEN 'ol-home0'
        WHEN '207.241.234.146' THEN 'ol-covers0'
        WHEN '207.241.234.180' THEN 'ol-web2'
        WHEN '207.241.236.242' THEN 'ol-web0'
        ELSE 'OTHER'
    END AS hostname
FROM pg_stat_activity
WHERE backend_start IS NOT NULL
ORDER BY hostname, backend_start
""".strip()


# ---------------------------------------------------------------------------
# Database query
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class ConnectionRow:
    """One row from pg_stat_activity."""

    pid: int
    backend_start: object  # datetime from psycopg2, or str fallback
    state: str
    session_age_seconds: float
    hostname: str


@dataclasses.dataclass
class ConnectionInfo(ConnectionRow):
    """A ConnectionRow enriched with its assigned stable ConnectionId."""

    connection_id: int


def fetch_connections() -> list[ConnectionRow]:
    """Query pg_stat_activity via psycopg2 and return parsed rows, or [] on error."""
    try:
        conn = psycopg2.connect(**_load_db_params(), connect_timeout=10)
        try:
            with conn.cursor() as cur:
                cur.execute(QUERY)
                columns = [desc[0] for desc in cur.description]
                raw_rows = [dict(zip(columns, row)) for row in cur.fetchall()]
        finally:
            conn.close()
    except psycopg2.Error as exc:
        print(f"  ERROR querying DB: {exc}")
        return []

    rows: list[ConnectionRow] = []
    for row in raw_rows:
        with contextlib.suppress(KeyError, ValueError, TypeError):
            rows.append(
                ConnectionRow(
                    pid=int(row["pid"]),
                    backend_start=row.get("backend_start", ""),
                    state=row.get("state") or "",
                    session_age_seconds=float(row.get("session_age_seconds") or 0),
                    hostname=row.get("hostname", "OTHER"),
                )
            )
    return rows


# ---------------------------------------------------------------------------
# State persistence  — {hostname: {pid: connection_id}}
# ---------------------------------------------------------------------------

State = dict[str, dict[int, int]]


def load_state() -> State:
    """Return persisted {hostname: {pid: connection_id}} mapping, or {} if none."""
    if STATE_FILE.exists():
        try:
            raw = json.loads(STATE_FILE.read_text())
            if any(not isinstance(v, dict) for v in raw.values()):
                return {}
            return {
                hostname: {int(pid): int(cid) for pid, cid in pids.items()}
                for hostname, pids in raw.items()
            }
        except (json.JSONDecodeError, ValueError, KeyError):
            pass
    return {}


def save_state(state: State) -> None:
    """Persist {hostname: {pid: connection_id}} mapping to disk."""
    STATE_FILE.write_text(
        json.dumps(
            {
                hostname: {str(pid): cid for pid, cid in pids.items()}
                for hostname, pids in state.items()
            },
            indent=2,
        )
    )


# ---------------------------------------------------------------------------
# CSV output
# ---------------------------------------------------------------------------


def ensure_csv_header() -> None:
    if not CSV_FILE.exists():
        with CSV_FILE.open("w", newline="") as fh:
            csv.DictWriter(fh, fieldnames=CSV_COLUMNS).writeheader()


def format_duration(total_seconds: float) -> str:
    s = int(total_seconds)
    h, remainder = divmod(s, 3600)
    m, sec = divmod(remainder, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}"


def parse_backend_start(ts) -> str:
    """Format a pg backend_start (datetime or string) as 'YYYY-MM-DD HH:MM:SS'."""
    if isinstance(ts, str):
        try:
            ts = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S.%f%z")
        except ValueError:
            return ts
    return ts.strftime("%Y-%m-%d %H:%M:%S")


def write_csv_rows(rows: list[ConnectionInfo]) -> None:
    now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    with CSV_FILE.open("a", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        for row in sorted(rows, key=lambda r: (r.hostname, r.connection_id)):
            writer.writerow(
                {
                    "Time": now_str,
                    "PID": row.pid,
                    "Hostname": row.hostname,
                    "ConnectionId": row.connection_id,
                    "StartTime": parse_backend_start(row.backend_start),
                    "TimeAlive": format_duration(row.session_age_seconds),
                    "State": row.state,
                }
            )


# ---------------------------------------------------------------------------
# Core function
# ---------------------------------------------------------------------------


def get_connection_metrics() -> list[ConnectionInfo]:
    """
    Fetch current DB connections, update persisted state, and return a list of
    ConnectionInfo objects suitable for submitting to Graphite or writing to CSV.

    State is loaded from and saved to disk on every call.
    """
    old_state = load_state()

    rows = fetch_connections()
    if not rows:
        return []

    # Sort so that older connections get lower connection IDs
    rows = sorted(rows, key=lambda row: row.session_age_seconds, reverse=True)

    by_hostname: dict[str, list[ConnectionRow]] = {}
    for row in rows:
        by_hostname.setdefault(row.hostname, []).append(row)
    state = {
        hostname: assign_stable_ids(
            [row.pid for row in hostname_rows], old_state.get(hostname, {})
        )
        for hostname, hostname_rows in by_hostname.items()
    }
    save_state(state)

    result: list[ConnectionInfo] = []
    for row in rows:
        conn_id = state.get(row.hostname, {}).get(row.pid)
        if conn_id is not None:
            result.append(
                ConnectionInfo(
                    pid=row.pid,
                    backend_start=row.backend_start,
                    state=row.state,
                    session_age_seconds=row.session_age_seconds,
                    hostname=row.hostname,
                    connection_id=conn_id,
                )
            )
    return result


# ---------------------------------------------------------------------------
# Main loop  (standalone usage)
# ---------------------------------------------------------------------------


def run_once() -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    metrics = get_connection_metrics()

    if not metrics:
        print(f"[{ts}] No connections returned.")
        return

    ensure_csv_header()
    write_csv_rows(metrics)

    by_host: dict[str, int] = {}
    for info in metrics:
        by_host[info.hostname] = by_host.get(info.hostname, 0) + 1
    host_summary = ", ".join(f"{h}={n}" for h, n in sorted(by_host.items()))
    print(f"[{ts}] Logged {len(metrics)} connection(s): {host_summary}")


def main() -> None:
    db = _load_db_params()
    print("DB connection monitor started.")
    print(f"  Host:      {db['host']}")
    print(f"  Database:  {db['dbname']}")
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
