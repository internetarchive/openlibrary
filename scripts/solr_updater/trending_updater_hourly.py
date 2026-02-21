import datetime
import itertools
import json
import subprocess
import sys
import threading
from collections import Counter
from dataclasses import dataclass
from math import sqrt

import requests

from openlibrary.core import db
from openlibrary.plugins.worksearch.code import execute_solr_query
from openlibrary.plugins.worksearch.search import get_solr

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


@dataclass
class LogLine:
    ip: str
    url: str
    page_key: str

    @staticmethod
    def from_line(line: str) -> 'LogLine':
        parts = line.split(' ')
        return LogLine(
            ip=parts[0],
            url=parts[6],
            page_key='/'.join(parts[6].split('/', 3)[0:3]),
        )


class NoLogsFoundError(subprocess.CalledProcessError):
    """
    Custom error to indicate that no logs were found for the given hour.
    This is used to differentiate between a real error and a case where no logs match the criteria.
    """

    pass


def get_logs_for_hour(dt: datetime.datetime, extra_grep: str | None = None):
    start_ts = int(dt.replace(minute=0, second=0, microsecond=0).timestamp() * 1000)
    end_ts = start_ts + 3600 * 1000 - 1

    if extra_grep:
        extra_grep = f'| {extra_grep}'

    # Note we use pretty aggressive filters to try to limit to non-automated traffic. Notably:
    # - Exclude out known bots as defined in scripts/obfi.sh
    # - Exclude HTTP/1.1 requests, which are likely from bots or automated scripts
    # - Exclude requests that don't have a referrer, which is likely a bot
    #
    # This yields ~4-6k requests per hour, which is a reasonable number to process
    with subprocess.Popen(
        f"""
            set -euo pipefail
            source scripts/obfi.sh
            obfi_range_files {start_ts} {end_ts} \
                | obfi_grep_bots -v \
                | obfi_grep_secondary_reqs -v \
                | grep -E 'GET /(works|books)/OL' \
                | grep -F ' 200 ' \
                | grep -F 'HTTP/2.' \
                | grep -vF ' "-" ' \
                | grep -vE '\\.(opds|json|rdf)' \
                | obfi_match_range {start_ts} {end_ts} \
                {extra_grep or ''} \
        """,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=True,
        text=True,
        executable='/bin/bash',
    ) as proc:
        assert proc.stdout

        def print_stderr(stderr):
            for err_line in stderr:
                err_line = err_line.strip()
                if err_line:
                    print(err_line, file=sys.stderr, flush=True)

        if proc.stderr:
            threading.Thread(
                target=print_stderr, args=(proc.stderr,), daemon=True
            ).start()
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue

            yield line

        proc.wait()
        match proc.returncode:
            case 0 | 141:
                pass
            case 1:
                # Note this case is ambiguous; grep throws a 1 when it receives no input,
                # but it could also be something else throwing a generic error
                raise NoLogsFoundError(proc.returncode, proc.args)
            case _:
                raise subprocess.CalledProcessError(proc.returncode, proc.args)


def fetch_work_hour_pageviews(dt: datetime.datetime) -> Counter[str]:
    """
    Iterate over the nginx logs of the given hour and count the number of pageviews
    """

    # We will need to fetch the work keys for these
    book_keys = {
        line.strip().split(' ')[1]
        for line in get_logs_for_hour(dt, 'grep -oE "GET /books/OL[0-9]+M"')
    }
    print(f"Found {len(book_keys)} /book pageviews in the hour")

    book_key_to_work_key: dict[str, str] = {}

    batch_size = 100
    batch_count = len(book_keys) // batch_size + 1
    print(f"Fetching corresponding work keys in {batch_count} batches: ")
    session = requests.Session()
    session.headers.update({'User-Agent': 'OpenLibrary Trending Updater'})
    # The API doesn't support POST requests, so need to use smaller batches
    # to avoid hitting the URL length limit.
    for i, batch in enumerate(itertools.batched(book_keys, batch_size)):
        print(f"\rBatch {i + 1}/{batch_count} ...", end='', flush=True)
        resp = session.get(
            'https://openlibrary.org/query.json',
            params={
                'query': json.dumps(
                    {
                        'type': '/type/edition',
                        'key': batch,
                        'works': None,
                        'limit': batch_size,
                    }
                ),
            },
        )
        resp.raise_for_status()
        data = resp.json()
        print(f"\rBatch {i + 1}/{batch_count} ... ✓ ", end='', flush=True)
        for edition in data:
            if not edition.get('works'):
                print(f"WARN: Edition {edition['key']} has no works, skipping")
                continue
            book_key_to_work_key[edition['key']] = edition['works'][0]['key']
    print()

    # Will want to dedupe by IP and work key, so we can count unique pageviews per work.
    # Each tuple is (ip, work_key).
    req_set: set[tuple[str, str]] = set()

    for line in get_logs_for_hour(dt):
        line = LogLine.from_line(line)
        page_key = line.page_key
        if page_key.startswith('/books/'):
            work_key = book_key_to_work_key.get(page_key, '')
            if not work_key:
                print(f"WARN: Could not find work key for {page_key}, skipping")
                continue

            req_set.add((line.ip, work_key))
        else:
            req_set.add((line.ip, page_key))

    return Counter(work_key for _, work_key in req_set)


def fetch_work_hour_book_events(dt: datetime.datetime) -> dict[str, int]:
    start = dt.replace(minute=0, second=0, microsecond=0)
    end_ts = start + datetime.timedelta(hours=1)

    ol_db = db.get_db()
    query = f"""
        SELECT work_id, COUNT(updated)
        FROM bookshelves_books
        WHERE updated >= '{start.isoformat()}' AND updated < '{end_ts.isoformat()}'
        GROUP BY work_id
    """
    result = {
        f'/works/OL{storage.work_id}W': storage.count for storage in ol_db.query(query)
    }
    print(f"{len(result)} works with bookshelf books in the given hour")
    return result


def fetch_solr_trending_data(hour_slot: int, work_keys: set[str]) -> list[dict]:
    docs = []
    solr_fields = (
        "key",
        "trending_score_hourly_sum",
        f'trending_score_hourly_{hour_slot}',
        "trending_score_daily_*",
    )

    # Docs with outdated values in the hour slot:
    print(f"Fetching works with existing trending data for hour slot {hour_slot}")
    resp = execute_solr_query(
        '/export',
        {
            "q": f'trending_score_hourly_{hour_slot}:[1 TO *]',
            "fl": ",".join(solr_fields),
            "sort": "key asc",
        },
        _timeout=None,  # No timeout for large datasets
    )
    assert resp
    data = resp.json()
    docs.extend(data["response"]["docs"])
    old_work_keys = {doc["key"] for doc in docs}

    if keys_to_fetch := work_keys - old_work_keys:
        print(f"Fetching {len(keys_to_fetch)} works without existing trending data")
        resp = execute_solr_query(
            '/export',
            {
                "q": ' OR '.join(f'key:"{key}"' for key in keys_to_fetch),
                "fl": ",".join(solr_fields),
                "sort": "key asc",
            },
            _timeout=None,  # No timeout for large datasets
        )
        assert resp
        data = resp.json()
        docs.extend(data["response"]["docs"])

    for doc in docs:
        # Ensure all expected fields are present, defaulting to 0 if missing
        for i in range(7):
            doc.setdefault(f"trending_score_daily_{i}", 0)
        doc.setdefault("trending_score_hourly_sum", 0)
        doc.setdefault(f"trending_score_hourly_{hour_slot}", 0)

    return docs


def compute_trending_value(pageviews_today: int, book_events_today: int) -> int:
    return pageviews_today + book_events_today * 10


def compute_trending_z_score(value_today: int, past_values: list[int]) -> float:
    """
    Calculate the trending z-score for the last 24h compared to the past events.
    I.e. How many standard deviations the current number of events is away from the mean
    of the past events.
    """
    past_sum = sum(past_values)
    # There are cases where clever bots/etc will hit a page hard causing it to go from 0
    # page views to 50+ pageviews in a single hour, which will skew the z-score.
    if (past_sum + value_today) < 30 or past_sum < 8:
        return 0.0
    N = len(past_values)
    past_mean = past_sum / N
    std_dev = sqrt(sum((x - past_mean) ** 2 for x in past_values) / N)
    return (value_today - past_mean) / (std_dev + 1.0)


def form_inplace_trending_update(
    solr_doc: dict,
    hour_slot: int,
    hour_value: int,
):
    new_hourly_sum = (
        solr_doc["trending_score_hourly_sum"]
        - solr_doc[f'trending_score_hourly_{hour_slot}']
        + hour_value
    )
    new_z_score = compute_trending_z_score(
        new_hourly_sum,
        [solr_doc.get(f'trending_score_daily_{i}', 0) for i in range(7)],
    )

    request_body = {
        "key": solr_doc["key"],
        f'trending_score_hourly_{hour_slot}': {"set": hour_value},
        "trending_score_hourly_sum": {"set": new_hourly_sum},
        "trending_z_score": {"set": new_z_score},
    }

    return request_body


def run_hourly_update(timestamp: str | None = None, dry_run: bool = False):
    if timestamp:
        ts = datetime.datetime.fromisoformat(timestamp)
    else:
        # Use previous hour if no timestamp is provided
        ts = datetime.datetime.now() - datetime.timedelta(hours=1)

    # The slot in solr that corresponds to the given hour
    hour_slot = ts.hour

    try:
        work_pageview = fetch_work_hour_pageviews(ts)
    except NoLogsFoundError as e:
        print(
            f"WARN: No pageviews found for hour {ts.isoformat()}. Error: {e}",
            file=sys.stderr,
        )
        work_pageview = Counter()

    work_book_events = fetch_work_hour_book_events(ts)
    keys_to_fetch = set(itertools.chain(work_pageview.keys(), work_book_events.keys()))
    solr_docs = fetch_solr_trending_data(hour_slot, keys_to_fetch)

    if not solr_docs:
        print("No new trending data found for the current hour.")
        return

    request_body = [
        form_inplace_trending_update(
            doc,
            hour_slot,
            compute_trending_value(
                work_pageview.get(doc["key"], 0),
                work_book_events.get(doc["key"], 0),
            ),
        )
        for doc in solr_docs
    ]
    print(f"{len(request_body)} works to update")
    if dry_run:
        print("Dry run mode enabled, not sending updates to Solr.")
    else:
        resp = get_solr().update_in_place(request_body, commit=True, _timeout=None)
        print(resp)
    print("Hourly update completed.")
