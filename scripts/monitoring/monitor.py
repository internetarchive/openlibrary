#!/usr/bin/env python
"""
Defines various monitoring jobs, that check the health of the system.
"""

import asyncio
import os
import re
import time

import httpx

from scripts.monitoring.fail2ban_monitor import get_fail2ban_counts
from scripts.monitoring.solr_updater_monitor import get_solr_updater_lag_event
from scripts.monitoring.utils import (
    GraphiteEvent,
    bash_run,
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
    309 BookshopLT/1.0 (***@gmail.com)
    230 BookReadingTime/2.0 (https://bookreadingtime.com; ***@bookreadingtime.com)
    180 CourseworkBot/1.0 (coursework@local)
    180 BookScraper/1.0 (data collection project; contact@example.com)
    177 Whefi/1.0 (***@whefi.com)
    160 BookEnricher/1.0 (your@email.com)
    102 AwarioSmartBot/1.0 (+https://awario.com/bots.html; ***@awario.com)
     85 Bookhives/1.0 (***@gmail.com)
     85 AliyunSecBot/Aliyun (***@service.alibaba.com)
     63 knihobot.cz (***@knihobot.cz)
     62 BookHub/1.0 (***@ybookshub.com)
     58 Bookscovery/1.0 (https://bookscovery.com; ***@bookscovery.com)
     52 VisionBooksAdminBot/1.0 (https://visionbooks.app/; ***@gmail.com) Node.js
     45 BookstoreApp/1.0 (***@thounkai.com)
     45 MonsoonFire-Portal/1.0 (+https://portal.monsoonfire.com; contact ***@monsoonfire.com)
     45 PrecodeZeoos/1.0 (***@precode.com.br)
     44 ReRoll/1.0 (rating-backfill; ***@gmail.com)
     39 ReRoll/1.0 (metadata-backfill; ***@gmail.com)
     36 OrelhaDoLivro/1.0 (***@orelhadelivro.com.br; openlibrary-summary)
     35 LikesnuBatch/1.0 (Contact: ***@likesnu.kr)
     28 EmberNovels/1.0 (***@embernovels.com)
     23 RAGAMUFFIN (***@gmail.com)
     22 booklist4u/1.0 (https://booklist4u.com; ***@gmail.com)
     21 TurkicMT-BookPipeline/1.0 (research; ***@example.com)
     20 Gleeph/1.0 (***@gleeph.net)
     18 LitCore/1.0 (https://litcore.io; ***@litcore.io) httpx/0.27
     12 ISBN.nu Book Price Comparison (***@isbn.nu)
      9 ISBNdb (***@isbndb.com)
      9 AsayaApp/1.0 (***@asaya.app)
      8 Sqwabl/1.0 (***@sqwabl.com)
      5 1000BooksBeforeKindergarten (***@1000booksfoundation.org)
      4 citesure/1.0 (***@citesure.com)
      4 Bibliogram (***@bibliogram.it)
      2 PERRLA/1.0 (***@perrla.com)
      2 Tomeki/1.0 (***@yopmail.com , gzip)
      2 Snipd/1.0 (https://www.snipd.com) contact: ***@snipd.com
      2 OnTrack/1.0 (***@gmail.com)
      2 Leaders.org (leaders.org) ***@leaders.org
      1 inventaire/5.0.0 (https://inventaire.io; ***@inventaire.io)
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


@limit_server(["ol-www0"], scheduler)
@scheduler.scheduled_job('interval', seconds=60)
def monitor_fail2ban():
    """Logs fail2ban nginx-429 jail stats (currently failed and banned counts)."""
    failed, banned = get_fail2ban_counts("nginx-429")
    ts = int(time.time())
    GraphiteEvent.submit_many(
        [
            GraphiteEvent(
                path="stats.ol.fail2ban.nginx-429.failed",
                value=float(failed),
                timestamp=ts,
            ),
            GraphiteEvent(
                path="stats.ol.fail2ban.nginx-429.banned",
                value=float(banned),
                timestamp=ts,
            ),
        ],
        GRAPHITE_URL,
    )


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
