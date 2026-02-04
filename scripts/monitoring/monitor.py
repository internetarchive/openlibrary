#!/usr/bin/env python
"""
Defines various monitoring jobs, that check the health of the system.
"""

import asyncio
import os
import re
import time

import httpx

from scripts.monitoring.haproxy_monitor import GraphiteEvent
from scripts.monitoring.solr_updater_monitor import get_solr_updater_lag_event
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
GRAPHITE_URL = "graphite.us.archive.org:2004"
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
    from scripts.monitoring.haproxy_monitor import main

    web_haproxy_ip = get_service_ip("web_haproxy")

    await main(
        haproxy_url=f'http://{web_haproxy_ip}:7072/admin?stats',
        graphite_address=GRAPHITE_URL,
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
    from scripts.monitoring.solr_logs_monitor import main

    main(
        solr_container=(
            'solr_builder-solr_prod-1' if SERVER == 'ol-solr1' else 'openlibrary-solr-1'
        ),
        graphite_prefix=f'stats.ol.{SERVER}',
        graphite_address=GRAPHITE_URL,
    )


@limit_server(["ol-www0"], scheduler)
@scheduler.scheduled_job('interval', seconds=60)
async def monitor_partner_useragents():

    def graphite_safe(s: str) -> str:
        """Normalize a string for safe use as a Graphite metric name."""
        # Replace dots and spaces with underscores
        s = s.replace('.', '_').replace(' ', '_')
        # Remove or replace unsafe characters
        s = re.sub(r'[^A-Za-z0-9_-]+', '_', s)
        # Collapse multiple underscores
        s = re.sub(r'_+', '_', s)
        # Strip leading/trailing underscores or dots
        return s.strip('._')

    def extract_agent_counts(ua_counts, allowed_names=None):
        agent_counts = {}
        for ua in ua_counts.strip().split("\n"):
            count, agent, *_ = ua.strip().split(" ")
            count = int(count)
            agent_name = graphite_safe(agent.split('/')[0])
            if not allowed_names or agent_name in allowed_names:
                agent_counts[agent_name] = count
            else:
                agent_counts.setdefault('other', 0)
                agent_counts['other'] += count
        return agent_counts

    known_names = extract_agent_counts("""
    177 Whefi/1.0 (contact@whefi.com)
     85 Bookhives/1.0 (paulpleela@gmail.com)
     85 AliyunSecBot/Aliyun (AliyunSecBot@service.alibaba.com)
     62 BookHub/1.0 (contact@ybookshub.com)
     58 Bookscovery/1.0 (https://bookscovery.com; info@bookscovery.com)
     45 BookstoreApp/1.0 (contact@thounkai.com)
     20 Gleeph/1.0 (contact-openlibrary@gleeph.net)
      2 Tomeki/1.0 (ankit@yopmail.com , gzip)
      2 Snipd/1.0 (https://www.snipd.com) contact: company@snipd.com
      2 OnTrack/1.0 (ashkan.haghighifashi@gmail.com)
      2 Leaders.org (leaders.org) janakan@leaders.org
      2 AwarioSmartBot/1.0 (+https://awario.com/bots.html; bots@awario.com)
      1 ISBNdb (support@isbndb.com)
    """)

    recent_uas = bash_run(
        """obfi_in_docker obfi_previous_minute | obfi_grep_bots -v | grep -Eo '[^"]+@[^"]+' | sort | uniq -c | sort -rn""",
        sources=["../obfi.sh"],
        capture_output=True,
    ).stdout

    agent_counts = extract_agent_counts(recent_uas, allowed_names=known_names)
    events = []
    ts = int(time.time())
    for agent, count in agent_counts.items():
        events.append(
            GraphiteEvent(
                path=f'stats.ol.partners.{agent}', value=float(count), timestamp=ts
            )
        )
    GraphiteEvent.submit_many(events, GRAPHITE_URL)


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
        ).submit(GRAPHITE_URL)


@limit_server(["ol-home0"], scheduler)
@scheduler.scheduled_job('interval', seconds=60)
async def monitor_solr_updater_lag():
    (await get_solr_updater_lag_event(solr_next=False)).submit(GRAPHITE_URL)
    (await get_solr_updater_lag_event(solr_next=True)).submit(GRAPHITE_URL)


async def main():
    scheduler.start()

    # Keep the main coroutine alive
    await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("[OL-MONITOR] Monitoring stopped.", flush=True)
