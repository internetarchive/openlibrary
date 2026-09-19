#!/usr/bin/env python
"""
Defines various monitoring jobs, that check the health of the system.
"""

import asyncio
import os
import time
from collections.abc import Iterable

import httpx

from scripts.monitoring.fail2ban_monitor import get_fail2ban_counts, get_jail_list
from scripts.monitoring.promotion import (
    RollingPromoter,
    parse_uniq_c,
    promoted_events,
    safe_label,
    tally,
)
from scripts.monitoring.solr_updater_monitor import get_solr_updater_lag_event
from scripts.monitoring.utils import (
    GraphiteEvent,
    bash_run,
    graphite_safe,
    limit_server,
)
from scripts.utils.scheduler import OlAsyncIOScheduler

HOST = os.getenv("HOSTNAME")  # eg "ol-www0.us.archive.org"

if not HOST:
    raise ValueError("HOSTNAME environment variable not set.")

SERVER = HOST.split(".")[0]  # eg "ol-www0"
GRAPHITE_URL = "graphite.us.archive.org:2004"
scheduler = OlAsyncIOScheduler("OL-MONITOR")

# Agents big enough to be worth their own grafana series get promoted out of the
# `other` bucket automatically, so neither list below has to be edited to keep up.
#
# The jobs tick once a minute, so the default 60-tick window is one hour and
# min_count is a per-hour floor: 75/hour is 1.25 req/min sustained, 50/hour is
# 0.83. max_labels is what actually bounds cardinality -- an agent has to out-rank
# everything else in the window to hold a slot, so a mistuned floor changes how
# far down the long tail we reach but not which agents get picked.
#
# Note this state lives in the process. The monitoring container restarts on
# deploy, which empties the window; the promoted set then rebuilds over the
# following hour.
CRAWLER_PROMOTER = RollingPromoter(min_count=75, max_labels=25)
PARTNER_PROMOTER = RollingPromoter(min_count=50, max_labels=50)


def submit_promoted_counts(
    counts: dict[str, int],
    promoter: RollingPromoter,
    prefix: str,
    pinned: Iterable[str] = (),
) -> None:
    """Label one tick's counts via ``promoter`` and submit them under ``prefix``."""
    events = promoted_events(counts, promoter, prefix, timestamp=int(time.time()), pinned=pinned)
    GraphiteEvent.submit_many(events, GRAPHITE_URL)


@limit_server(["ol-web*", "ol-covers0"], scheduler)
@scheduler.scheduled_job("interval", seconds=60)
def log_workers_cur_fn():
    """Logs the state of the gunicorn workers."""
    bash_run(
        f"log_workers_cur_fn webpy stats.{SERVER}.workers.webpy.cur_fn",
        sources=["olspy.sh"],
    )
    bash_run(
        f"log_workers_cur_fn fastapi stats.{SERVER}.workers.fastapi.cur_fn",
        sources=["olspy.sh"],
    )


@limit_server(["ol-www0", "ol-covers0"], scheduler)
@scheduler.scheduled_job("interval", seconds=60)
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

    bash_run(
        f"log_top_response_times stats.{bucket}.response_times",
        sources=["../obfi.sh", "utils.sh"],
    )

    # Bots that self-identify but aren't in obfi_grep_bots' list. The high-volume
    # ones get their own series; the rest sum into `other`, which log_recent_bot_traffic
    # used to emit as an undifferentiated line count.
    unknown_bot_counts = bash_run(
        "list_unknown_bot_counts",
        sources=["../obfi.sh", "utils.sh"],
        capture_output=True,
    ).stdout
    submit_promoted_counts(
        counts=tally(parse_uniq_c(unknown_bot_counts), key=safe_label),
        promoter=CRAWLER_PROMOTER,
        prefix=f"stats.{bucket}.bot_traffic",
    )


@limit_server(["ol-solr0", "ol-solr1", "ol-solr2"], scheduler)
@scheduler.scheduled_job("interval", seconds=60)
async def monitor_solr():
    # Note this is a long-running job that does its own scheduling.
    # But by having it on a 60s interval, we ensure it restarts if it fails.
    from scripts.monitoring.solr_logs_monitor import main

    match SERVER:
        case "ol-solr0":
            solr_container = "openlibrary-solr-1"
        case "ol-solr1":
            solr_container = "solr_builder-solr_prod-1"
        case "ol-solr2":
            solr_container = "openlibrary-solr_replica-1"

    main(
        solr_container=solr_container,
        graphite_prefix=f"stats.ol.{SERVER}",
        graphite_address=GRAPHITE_URL,
    )


# Partner agents that always get their own series, however quiet they go.
#
# This snapshot of a previous run used to gate labelling entirely -- anything
# absent from it collapsed into `other`, which is why `other` grew to dwarf every
# labelled partner. It is now only a pin list: new partners are promoted on volume
# (see scripts/monitoring/promotion.py), so it no longer has to be edited to keep
# up, and an entry can be dropped whenever that partner stops being worth a line.
PINNED_PARTNER_UAS = """
   4307 Bontent/1.0 (https://bontent.app; ***@bontent.app)
    403 Research-Cover-Scraper (***@cornell.edu)
    309 BookshopLT/1.0 (***@gmail.com)
    271 BookReadingTime/2.0 (https://bookreadingtime.com; ***@bookreadingtime.com)
    244 Roolio/1.0 (https://roolio.app; contact: ***@roolio.app)
    182 TooManyBooks/1.0 (***@gmail.com)
    180 CourseworkBot/1.0 (coursework@local)
    180 BookScraper/1.0 (data collection project; contact@example.com)
    180 librimondo-pim/1.0 (https://librimondo.com; ***@fkwt.pl)
    180 WikiNerd (***@wikinerd.com.br)
    179 Blurbit/1.0 (***@blurbit.com)
    179 BusinessBiographies/1.0 (research; ***@gmail.com)
    179 isbn-book-crawler/1.0 (educational)
    179 GoodreadsEnricher/1.0 (+***@***)
    177 CourseProjectAPI/1.0 (your@email.com)
    177 Whefi/1.0 (***@whefi.com)
    176 Tomeki/1.0 (***@yopmail.com , gzip)
    173 afin-app/1.0 (taste recommendation; ***@gmail.com)
    165 Pinakes-POC/0.1 (SNU Library; mailto:***@library.snu.ac.kr)
    160 BookEnricher/1.0 (your@email.com)
    153 OrelhaDoLivro/1.0 (***@orelhadelivro.com.br; openlibrary-summary)
    146 KalamoBooks-Enrichment/1.0 (contacto: ***@gmail.com)
    130 KuratoPublisherSweep/1.0 (***@gmail.com)
    129 TimberdoodleReading/0.1 (***@timberdoodle.com)
    126 KiveoAPI/1.0 (***@kiveo.app)
    111 BookInClub/1.0 (https://bookinclub.com; ***@bookinclub.com) node.js/axios
    108 WonderclubBot/1.0 (wonderclub.com)
    107 BookDirectoryBot/1.0 (contact: ***@gmail.com)
    107 Shellf.app (***@shellf.app)
    102 AwarioSmartBot/1.0 (+https://awario.com/bots.html; ***@awario.com)
     99 KkodecsBookBot/0.1.0-alpha5 (Livrarr; ***@proton.me; https://github.com/kkodecs/livrarr)
     85 Bookhives/1.0 (***@gmail.com)
     85 AliyunSecBot/Aliyun (***@service.alibaba.com)
     84 ASCENDCHESS/1.0 (Chess Training Platform; ***@ascendchess.com)
     78 PeoopleEnrichmentBot/1.0 (contact: ***@peoople.app)
     76 Lovvit-Archive/1.0 (https://lovvit.jp; ***@lovvit.jp)
     75 Bookscovery/1.0 (https://bookscovery.com; ***@bookscovery.com)
     73 Pinakes-POC/0.1 (SNU Library; mailto:***@library.snu.ac.kr)
     66 wiib-aitm-frbr/1.0 (***@gmail.com)
     65 PejibooksBot/1.0
     64 UMDB/1.0 (+https://umdb.app; contact: ***@gmail.com)
     63 knihobot.cz (***@knihobot.cz)
     62 BookHub/1.0 (***@ybookshub.com)
     62 SafAI-EgitimBotu/3.0 (egitim amacli; iletisim: safai@example.com)
     61 siftivo-import-from-seed (***@siftivo.com)
     52 VisionBooksAdminBot/1.0 (https://visionbooks.app/; ***@gmail.com) Node.js
     51 chieveme.com (***@gmail.com)
     47 BookiBot/1.0 (+https://booki.se; ***@booki.se)
     46 Homebranch (self-hosted e-book library; ***@gmail.com)
     46 KuraReads/1.0 (contact@example.org)
     45 BookstoreApp/1.0 (***@thounkai.com)
     45 MonsoonFire-Portal/1.0 (+https://portal.monsoonfire.com; contact ***@monsoonfire.com)
     45 PrecodeZeoos/1.0 (***@precode.com.br)
     44 ReRoll/1.0 (rating-backfill; ***@gmail.com)
     39 ReRoll/1.0 (metadata-backfill; ***@gmail.com)
     44 UniversalHistoryBot/1.0 (contact: your@email.com)
     42 PageLabCrawler/0.1 (https://pagelab.orbytgames.com; contact: ***@example.com)
     40 BookTidy2-personal-library-tool/1.0 (contact: ***@gmail.com)
     37 torrenty-enrich/1.0 (metadata enrichment; contact: ***@simpledev.cz)
     35 Bibcitation (***@bibcitation.com)
     35 LikesnuBatch/1.0 (Contact: ***@likesnu.kr)
     32 eBookShelf/1.0 (***@gmail.com)
     32 WonderclubBot/1.0 (+https://wonderclub.com; ***@gmail.com)
     32 SMS4Smile-Enricher/1.0 (***@sms4smile.com)
     28 EmberNovels/1.0 (***@embernovels.com)
     24 DMDB/1.0 (https://dmdb.com; ***@dmdb.com)
     23 RAGAMUFFIN (***@gmail.com)
     22 booklist4u/1.0 (https://booklist4u.com; ***@gmail.com)
     22 rvbolio-calibre-classifier/1.0 (personal library; contact ***@tramacomunicacion.com)
     21 TurkicMT-BookPipeline/1.0 (research; ***@example.com)
     20 BetterReads/0.1 (book-tracking-app; ***@betterreadsapp.com)
     20 Gleeph/1.0 (***@gleeph.net)
     20 ReadingList/2.8.11 (***@readinglist.app)
     18 LitCore/1.0 (https://litcore.io; ***@litcore.io) httpx/0.27
     12 ISBN.nu Book Price Comparison (***@isbn.nu)
     11 montheque/0.1 (personal project; contact: ***@proton.me)
     10 rare-books-intel/1.0 (***@gmail.com)
      9 ISBNdb (***@isbndb.com)
      9 AsayaApp/1.0 (***@asaya.app)
      6 LibRoomApp/1.0 (***@gmail.com)
      6 LoverOfBooks/1.0 (***@sunnyengineer.com)
      6 Romancy/1.0 (***@romancy.app)
      6 Spines/1.0 (github.com/fresheggdesigns/spines; ***@gmail.com)
      8 Sqwabl/1.0 (***@sqwabl.com)
      5 1000BooksBeforeKindergarten (***@1000booksfoundation.org)
      4 citesure/1.0 (***@citesure.com)
      4 Bibliogram (***@bibliogram.it)
      2 PERRLA/1.0 (***@perrla.com)
      2 Snipd/1.0 (https://www.snipd.com) contact: ***@snipd.com
      2 OnTrack/1.0 (***@gmail.com)
      2 Leaders.org (leaders.org) ***@leaders.org
      1 inventaire/5.0.0 (https://inventaire.io; ***@inventaire.io)
    """


def partner_label(user_agent: str) -> str:
    """Label a partner by the first token of its UA, eg `Bontent/1.0 (...)` -> `Bontent`."""
    return safe_label(user_agent.split(maxsplit=1)[0].split("/", maxsplit=1)[0])


PINNED_PARTNER_NAMES = set(tally(parse_uniq_c(PINNED_PARTNER_UAS), key=partner_label))


@limit_server(["ol-www0"], scheduler)
@scheduler.scheduled_job("interval", seconds=60)
async def monitor_partner_useragents():
    recent_uas = bash_run(
        """obfi_in_docker obfi_previous_minute | obfi_grep_bots -v | grep -Eo '[^"]+@[^"]+' | sort | uniq -c | sort -rn""",
        sources=["../obfi.sh"],
        capture_output=True,
    ).stdout

    submit_promoted_counts(
        counts=tally(parse_uniq_c(recent_uas), key=partner_label),
        promoter=PARTNER_PROMOTER,
        prefix="stats.ol.partners",
        pinned=PINNED_PARTNER_NAMES,
    )


@limit_server(["ol-www0"], scheduler)
@scheduler.scheduled_job("interval", seconds=60)
async def monitor_empty_homepage():
    async with httpx.AsyncClient() as client:
        ts = int(time.time())
        response = await client.get("https://openlibrary.org")
        book_count = response.text.count('<div class="book ')
        GraphiteEvent(
            path="stats.ol.homepage_book_count",
            value=book_count,
            timestamp=ts,
        ).submit(GRAPHITE_URL)


@limit_server(["ol-www0"], scheduler)
@scheduler.scheduled_job("interval", seconds=60)
def monitor_fail2ban():
    """Logs fail2ban jail stats (currently failed and banned counts) for every configured jail."""
    ts = int(time.time())
    events = []
    for jail in get_jail_list():
        failed, banned = get_fail2ban_counts(jail)
        jail_bucket = graphite_safe(jail)
        events.append(
            GraphiteEvent(
                path=f"stats.ol.fail2ban.{jail_bucket}.failed",
                value=float(failed),
                timestamp=ts,
            )
        )
        events.append(
            GraphiteEvent(
                path=f"stats.ol.fail2ban.{jail_bucket}.banned",
                value=float(banned),
                timestamp=ts,
            )
        )
    GraphiteEvent.submit_many(events, GRAPHITE_URL)


@limit_server(["ol-home0"], scheduler)
@scheduler.scheduled_job("interval", seconds=60)
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
    except KeyboardInterrupt, SystemExit:
        print("[OL-MONITOR] Monitoring stopped.", flush=True)
