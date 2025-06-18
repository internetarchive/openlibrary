import datetime
from math import sqrt

import _init_path  # noqa: F401 Imported for its side effect of setting PYTHONPATH

from openlibrary.config import load_config
from openlibrary.core import db
from openlibrary.plugins.worksearch.code import execute_solr_query
from openlibrary.plugins.worksearch.search import get_solr
from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI

# This script handles hourly updating of each works' z-score. The 'trending_score_hourly_23' field is
# ignored, and the current count of bookshelves events in the last hour is the new trending_score_hourly[0]
# value, with each other value incrementing up by one.

# Trending_score_daily values are all fetched in order to calculate their mean and standard deviation.
# The formula for the new z-score is [ z = sum(trending_score_hourly_*) - mean(trending_score_daily_*) /  (standard_deviation(trending_score_daily)] + 1).
# The incrementation of the denominator by 1 serves several purposes:
#       - It prevents divide-by-zero errors on objects with 0s in all trending_score_daily_* values, which is important,
#         as they are instantiated to that upon the first time solr reindexes them with this new information.
#       - It serves to deemphasize such values, as we're not particularly interested in a shift from
#         0 events to 1 event.


def fetch_works_trending_scores(current_hour: int, timestamp: datetime.datetime):
    ol_db = db.get_db()
    # Use the provided timestamp for the time window
    query = f"""
        SELECT work_id, COUNT(updated)
        FROM bookshelves_books
        WHERE updated >= '{timestamp - datetime.timedelta(hours=1)}' AND updated < '{timestamp}'
        GROUP BY work_id
    """
    db_data = {
        f'/works/OL{storage.work_id}W': storage.count
        for storage in list(ol_db.query(query))
    }
    print(f"{len(db_data)} works with bookshelf books in the last hour")

    resp = execute_solr_query(
        '/export',
        {
            "q": (
                f'trending_score_hourly_{current_hour}:[1 TO *]'
                + (" OR " if db_data != {} else "")
                + (" OR ".join(["key:\"" + key + "\"" for key in db_data]))
            ),
            "fl": ",".join(
                [
                    "key",
                    "trending_score_hourly_sum",
                    f'trending_score_hourly_{current_hour}',
                    "trending_score_daily_*",
                ]
            ),
            "sort": "key asc",
        },
        _timeout=10_000,  # Increase timeout for large datasets
    )

    assert resp

    data = resp.json()
    for doc in data["response"]["docs"]:
        # Ensure all expected fields are present, defaulting to 0 if missing
        for i in range(7):
            doc.setdefault(f"trending_score_daily_{i}", 0)
        doc.setdefault("trending_score_hourly_sum", 0)
        doc.setdefault(f"trending_score_hourly_{current_hour}", 0)
    return {
        doc["key"]: {"count": db_data.get(doc["key"], 0), "solr_doc": doc}
        for doc in data["response"]["docs"]
    }


# If the arithmetic mean is below 10/7 (i.e: there have been)
# less than 10 reading log events for the work in the past week,
# it should not show up on trending.
AVERAGE_DAILY_EVENTS_FLOOR = 10 / 7


# This function calculates how many standard deviations the value for the last
# 24 hours is away from the mean.
def get_z_score(solr_doc: dict, count: int, current_hour: int):
    arith_mean = sum([solr_doc[f'trending_score_daily_{i}'] for i in range(7)]) / 7
    if arith_mean < AVERAGE_DAILY_EVENTS_FLOOR:
        return 0
    last_24_hours_value = (
        solr_doc['trending_score_hourly_sum']
        + count
        - solr_doc[f'trending_score_hourly_{current_hour}']
    )
    st_dev = sqrt(
        sum(
            [
                pow(solr_doc[f'trending_score_daily_{i}'] - arith_mean, 2)
                for i in range(7)
            ]
        )
        / 7
    )
    return (last_24_hours_value - arith_mean) / (st_dev + 1.0)


def form_inplace_updates(work_id: str, count: int, solr_doc: dict, current_hour: int):
    request_body = {
        "key": work_id,
        f'trending_score_hourly_{current_hour}': {"set": count},
        "trending_score_hourly_sum": {
            "set": solr_doc["trending_score_hourly_sum"]
            - solr_doc[f'trending_score_hourly_{current_hour}']
            + count
        },
        "trending_z_score": {"set": get_z_score(solr_doc, count, current_hour)},
    }

    return request_body


def main(openlibrary_yml: str, timestamp: str | None = None):
    load_config(openlibrary_yml)

    if timestamp:
        ts = datetime.datetime.fromisoformat(timestamp)
    else:
        ts = datetime.datetime.now()
    current_hour = ts.hour
    if work_data := fetch_works_trending_scores(current_hour, ts):
        request_body = [
            form_inplace_updates(
                work_id,
                work_data[work_id]["count"],
                work_data[work_id]["solr_doc"],
                current_hour,
            )
            for work_id in work_data
        ]
        print(f"{len(request_body)} works to update")
        resp = get_solr().update_in_place(request_body, commit=True)
        print(resp)
        print("Hourly update completed.")


if __name__ == '__main__':
    FnToCLI(main).run()
