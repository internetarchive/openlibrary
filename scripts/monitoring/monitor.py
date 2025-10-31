#!/usr/bin/env python
"""
Defines various monitoring jobs, that check the health of the system.
"""

import asyncio
import os
import time

import httpx

from scripts.monitoring.haproxy_monitor import GraphiteEvent
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
def monitor_nginx_logs():
    """Logs recent bot traffic, HTTP statuses, and top IP counts."""
    match SERVER:
        case "ol-www0":
            bucket = "ol"
        case "ol-covers0":
            bucket = "ol-covers"
        case _:
            raise ValueError(f"Unknown server: {SERVER}")

    bash_run(
        f"log_recent_bot_traffic stats.{bucket}.bot_traffic",
        sources=["../obfi.sh", "utils.sh"],
    )
    bash_run(
        f"log_recent_http_statuses stats.{bucket}.http_status",
        sources=["../obfi.sh", "utils.sh"],
    )
    bash_run(
        f"log_top_ip_counts stats.{bucket}.top_ips",
        sources=["../obfi.sh", "utils.sh"],
    )


@limit_server(["ol-www0"], scheduler)
@scheduler.scheduled_job('interval', seconds=60)
async def monitor_haproxy():
    # Note this is a long-running job that does its own scheduling.
    # But by having it on a 60s interval, we ensure it restarts if it fails.
    from scripts.monitoring.haproxy_monitor import main  # noqa: PLC0415

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


@limit_server(["ol-solr0", "ol-solr1"], scheduler)
@scheduler.scheduled_job('interval', seconds=60)
async def monitor_solr():
    # Note this is a long-running job that does its own scheduling.
    # But by having it on a 60s interval, we ensure it restarts if it fails.
    from scripts.monitoring.solr_logs_monitor import main  # noqa: PLC0415

    main(
        solr_container=(
            'solr_builder-solr_prod-1' if SERVER == 'ol-solr1' else 'openlibrary-solr-1'
        ),
        graphite_prefix=f'stats.ol.{SERVER}',
        graphite_address='graphite.us.archive.org:2004',
    )


@limit_server(["ol-www0"], scheduler)
@scheduler.scheduled_job('interval', seconds=60)
async def monitor_empty_homepage():
    async with httpx.AsyncClient() as client:
        ts = int(time.time())
        response = await client.get('https://openlibrary.org')
        book_count = response.text.count('<div class="book ')
        GraphiteEvent(
            path="stats.ol.homepage_book_count",
            value=book_count,
            timestamp=ts,
        ).submit('graphite.us.archive.org:2004')


async def main():
    scheduler.start()

    # Keep the main coroutine alive
    await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("[OL-MONITOR] Monitoring stopped.", flush=True)
