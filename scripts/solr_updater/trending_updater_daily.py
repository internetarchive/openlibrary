import datetime

from openlibrary.plugins.worksearch.code import execute_solr_query
from openlibrary.plugins.worksearch.search import get_solr


def fetch_works_trending_scores(current_day: int):
    resp = execute_solr_query(
        '/export',
        {
            "q": f'trending_score_hourly_sum:[1 TO *] OR trending_score_daily_{current_day}:[1 TO *]',
            "fl": "key,trending_score_hourly_sum",
            # /export needs a sort to work
            "sort": "key asc",
        },
        _timeout=None,  # No timeout for large datasets
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
