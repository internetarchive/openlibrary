#!/usr/bin/env python
"""
Defines various monitoring jobs, that check the health of the system.
"""

import asyncio
import os
import re
import time

import httpx
from typing import Any

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
        graphite_address='graphite.us.archive.org:2004',
    )


@limit_server(["ol-www0"], scheduler)
@scheduler.scheduled_job('interval', seconds=60)
def monitor_partner_useragents():

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

    def extract_agent_counts(
        ua_counts: str,
        allowed_names: dict[str, Any] | set[str] | None = None,
    ):
        agent_counts: dict[str, int] = {}
        for ua_line in ua_counts.strip().split("\n"):
            ua_line = ua_line.strip()
            if not ua_line:
                continue

            count_str, agent, *_ = ua_line.split(" ")
            count = int(count_str)
            agent_name = graphite_safe(agent.split('/')[0])
            if not allowed_names or agent_name in allowed_names:
                agent_counts[agent_name] = count
            else:
                agent_counts.setdefault('other', 0)
                agent_counts['other'] += count
        return agent_counts

    known_names = extract_agent_counts(
        """
   1771 BookHub/1.0 (***@ybookshub.com)
   1757 Whefi/1.0 (***@whefi.com)
    788 Bookhives/1.0 (***@gmail.com)
    629 Bookscovery/1.0 (https://bookscovery.com; ***@bookscovery.com)
    387 ISBNdb (***@isbndb.com)
    243 knihobot.cz (***@knihobot.cz)
     91 Librarian-App/1.0 (***@librarian.app)
     62 Gleeph/1.0 (***@gleeph.net)
     62 AliyunSecBot/Aliyun (***@service.alibaba.com)
     33 Garden-iOS/1.0 (contact: ***@example.com)
     30 BookSlayer (***@bookslayer.io)
     29 AwarioSmartBot/1.0 (+https://awario.com/bots.html; ***@awario.com)
     23 LibRoomApp/1.0 (***@gmail.com)
     19 ignisda/ryot-v9.4.4 (***@gmail.com)
     17 PrecodeZeoos/1.0 (***@precode.com.br)
     17 Leaders.org (leaders.org) ***@leaders.org
     10 GPTZero (***@gptzero.me)
      7 Tomeki/1.0 (***@yopmail.com , gzip)
      4 ignisda/ryot-v9.4.1 (***@gmail.com)
      3 Snipd/1.0 (https://www.snipd.com) contact: ***@snipd.com
      3 citesure/1.0 (***@citesure.com)
      2 Pleroma 2.9.0; https://social.solarpunk.au <***@riseup.net>; Bot
      2 ignisda/ryot-v8.9.4 (***@gmail.com)
      1 Librish/1.0 (***@librish.app)
    """
    )

    ts = int(time.time())
    recent_uas = bash_run(
        """obfi_in_docker obfi_previous_minute | obfi_grep_bots -v | grep -Eo '[^"]+@[^"]+' | sort | uniq -c | sort -rn""",
        sources=["../obfi.sh"],
        capture_output=True,
    ).stdout

    agent_counts = extract_agent_counts(recent_uas, allowed_names=known_names)
    events = []
    for agent, count in agent_counts.items():
        events.append(
            GraphiteEvent(
                path=f'stats.ol.partners.{agent}', value=float(count), timestamp=ts
            )
        )
    GraphiteEvent.submit_many(events, 'graphite.us.archive.org:2004')


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
