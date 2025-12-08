import datetime
import logging
import time

import httpx

from openlibrary.plugins.worksearch.code import execute_solr_query
from openlibrary.plugins.worksearch.search import get_solr

logger = logging.getLogger("openlibrary.trending-updater-daily")

MAX_RETRIES = 12  # 2 minutes with exponential backoff starting at 5s
INITIAL_WAIT_SECONDS = 5


def wait_for_solr():
    """Wait for Solr to become available with exponential backoff."""
    solr = get_solr()
    wait_time = INITIAL_WAIT_SECONDS

    for attempt in range(MAX_RETRIES):
        try:
            resp = solr.session.get(
                f"{solr.base_url}/admin/ping",
                timeout=5,
            )
            if resp.status_code == 200:
                logger.info("Solr is available")
                return True
        except (httpx.HTTPError, httpx.ConnectError) as e:
            logger.warning(
                "Solr not ready (attempt %d/%d): %s", attempt + 1, MAX_RETRIES, e
            )

        if attempt < MAX_RETRIES - 1:
            logger.info("Waiting %ds before retrying...", wait_time)
            time.sleep(wait_time)
            wait_time = min(wait_time * 1.5, 30)  # Cap at 30 seconds

    raise RuntimeError("Solr is not available after maximum retries")


def fetch_works_trending_scores(current_day: int):
    wait_for_solr()

    resp = execute_solr_query(
        '/export',
        {
            "q": f'trending_score_hourly_sum:[1 TO *] OR trending_score_daily_{current_day}:[1 TO *]',
            "fl": "key,trending_score_hourly_sum",
            "sort": "key asc",
        },
        _timeout=None,
    )
    assert resp
    data = resp.json()
    doc_data = {
        doc["key"]: doc.get("trending_score_hourly_sum", 0)
        for doc in data["response"]["docs"]
    }
    return doc_data


def form_inplace_updates(work_id: str, current_day: int, new_value: int):
    return {"key": work_id, f'trending_score_daily_{current_day}': {"set": new_value}}


def run_daily_update(timestamp: str | None = None, dry_run: bool = False):
    if timestamp:
        ts = datetime.datetime.fromisoformat(timestamp)
    else:
        ts = datetime.datetime.now()
    current_day = ts.weekday()
    work_data = fetch_works_trending_scores(current_day)

    request_body = [
        form_inplace_updates(work_id, current_day, work_data[work_id])
        for work_id in work_data
    ]

    print(f"{len(request_body)} works to update with daily trending scores.")
    if dry_run:
        print("Dry run mode, not sending updates to Solr.")
    else:
        resp = get_solr().update_in_place(request_body, commit=True, _timeout=None)
        print(resp)
    print("Daily update completed.")
