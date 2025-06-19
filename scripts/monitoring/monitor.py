#!/usr/bin/env python
"""
Defines various monitoring jobs, that check the health of the system.
"""

import asyncio
import os

from scripts.monitoring.utils import (
    bash_run,
    get_service_ip,
    limit_server,
)
from scripts.utils.scheduler import OlAsyncIOScheduler

HOST = os.getenv("HOSTNAME")  # eg "ol-www0.us.archive.org"

if not HOST:
    raise ValueError("HOSTNAME environment variable not set.")

SERVER = HOST.split(".")[0]  # eg "ol-www0"
scheduler = OlAsyncIOScheduler("OL-MONITOR")


@limit_server(["ol-web*", "ol-covers0"], scheduler)
@scheduler.scheduled_job('interval', seconds=60)
def log_workers_cur_fn():
    """Logs the state of the gunicorn workers."""
    bash_run(f"log_workers_cur_fn stats.{SERVER}.workers.cur_fn", sources=["utils.sh"])


@limit_server(["ol-www0", "ol-covers0"], scheduler)
@scheduler.scheduled_job('interval', seconds=60)
def log_recent_bot_traffic():
    """Logs the state of the gunicorn workers."""
    match SERVER:
        case "ol-www0":
            bucket = "ol"
            container = "openlibrary-web_nginx-1"
        case "ol-covers0":
            bucket = "ol-covers"
            container = "openlibrary-covers_nginx-1"
        case _:
            raise ValueError(f"Unknown server: {SERVER}")

    bash_run(
        f"log_recent_bot_traffic stats.{bucket}.bot_traffic {container}",
        sources=["utils.sh"],
    )


@limit_server(["ol-www0", "ol-covers0"], scheduler)
@scheduler.scheduled_job('interval', seconds=60)
def log_recent_http_statuses():
    """Logs the recent HTTP statuses."""
    match SERVER:
        case "ol-www0":
            bucket = "ol"
            container = "openlibrary-web_nginx-1"
        case "ol-covers0":
            bucket = "ol-covers"
            container = "openlibrary-covers_nginx-1"
        case _:
            raise ValueError(f"Unknown server: {SERVER}")

    bash_run(
        f"log_recent_http_statuses stats.{bucket}.http_status {container}",
        sources=["utils.sh"],
    )


@limit_server(["ol-www0", "ol-covers0"], scheduler)
@scheduler.scheduled_job('interval', seconds=60)
def log_top_ip_counts():
    """Logs the recent HTTP statuses."""
    match SERVER:
        case "ol-www0":
            bucket = "ol"
            container = "openlibrary-web_nginx-1"
        case "ol-covers0":
            bucket = "ol-covers"
            container = "openlibrary-covers_nginx-1"
        case _:
            raise ValueError(f"Unknown server: {SERVER}")

    bash_run(
        f"log_top_ip_counts stats.{bucket}.top_ips {container}",
        sources=["utils.sh"],
    )


@limit_server(["ol-www0"], scheduler)
@scheduler.scheduled_job('interval', seconds=60)
async def monitor_haproxy():
    # Note this is a long-running job that does its own scheduling.
    # But by having it on a 60s interval, we ensure it restarts if it fails.
    from scripts.monitoring.haproxy_monitor import main

    web_haproxy_ip = get_service_ip("web_haproxy")

    await main(
        haproxy_url=f'http://{web_haproxy_ip}:7072/admin?stats',
        graphite_address='graphite.us.archive.org:2004',
        prefix='stats.ol.haproxy',
        dry_run=False,
        fetch_freq=10,
        commit_freq=30,
        agg=None,  # No aggregation
    )


async def main():
    scheduler.start()

    # Keep the main coroutine alive
    await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("[OL-MONITOR] Monitoring stopped.", flush=True)
