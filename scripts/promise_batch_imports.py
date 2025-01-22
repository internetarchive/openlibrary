"""
As of 2022-12: Run on `ol-home0 cron container as

```
$ ssh -A ol-home0
$ docker exec -it -uopenlibrary openlibrary-cron-jobs-1 bash
$ PYTHONPATH="/openlibrary" python3 /openlibrary/scripts/promise_batch_imports.py /olsystem/etc/openlibrary.yml
```

The imports can be monitored for their statuses and rolled up / counted using this query on `ol-db1`:

```
=# select count(*) from import_item where batch_id in (select id from import_batch where name like 'bwb_daily_pallets_%');
```
"""

from __future__ import annotations

import datetime
import json
import logging
from typing import Any
from urllib.parse import urlencode

import _init_path  # noqa: F401 Imported for its side effect of setting PYTHONPATH
import ijson
import requests

from infogami import config  # noqa: F401 side effects may be needed
from openlibrary.config import load_config
from openlibrary.core import stats
from openlibrary.core.imports import Batch
from openlibrary.core.vendors import stage_bookworm_metadata
from openlibrary.plugins.upstream.utils import safeget
from openlibrary.utils.isbn import to_isbn_13
from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI

logger = logging.getLogger("openlibrary.importer.promises")


def format_date(date: str, only_year: bool) -> str:
    """
    Format date as "yyyy-mm-dd" or only "yyyy"

    :param date: Date in "yyyymmdd" format.
    """
    return date[:4] if only_year else f"{date[0:4]}-{date[4:6]}-{date[6:8]}"


def map_book_to_olbook(book, promise_id):
    def clean_null(val: str | None) -> str | None:
        if val in ('', 'null', 'null--'):
            return None
        return val

    asin_is_isbn_10 = book.get('ASIN') and book.get('ASIN')[0].isdigit()
    product_json = book.get('ProductJSON', {})
    publish_date = clean_null(product_json.get('PublicationDate'))
    title = product_json.get('Title')
    isbn = book.get('ISBN') or ' '
    sku = book['BookSKUB'] or book['BookSKU'] or book['BookBarcode']
    olbook = {
        'local_id': [f"urn:bwbsku:{sku.upper()}"],
        'identifiers': {
            **({'amazon': [book.get('ASIN')]} if not asin_is_isbn_10 else {}),
            **({'better_world_books': [isbn]} if not is_isbn_13(isbn) else {}),
        },
        **({'isbn_13': [isbn]} if is_isbn_13(isbn) else {}),
        **({'isbn_10': [book.get('ASIN')]} if asin_is_isbn_10 else {}),
        **({'title': title} if title else {}),
        'authors': (
            [{"name": clean_null(product_json.get('Author'))}]
            if clean_null(product_json.get('Author'))
            else []
        ),
        'publishers': [clean_null(product_json.get('Publisher')) or '????'],
        'source_records': [f"promise:{promise_id}:{sku}"],
        # format_date adds hyphens between YYYY-MM-DD, or use only YYYY if date is suspect.
        'publish_date': (
            format_date(
                date=publish_date, only_year=publish_date[-4:] in ('0000', '0101')
            )
            if publish_date
            else ''
        ),
    }
    if not olbook['identifiers']:
        del olbook['identifiers']
    return olbook


def is_isbn_13(isbn: str):
    """
    Naive check for ISBN-13 identifiers.

    Returns true if given isbn is in ISBN-13 format.
    """
    return isbn and isbn[0].isdigit()


def stage_incomplete_records_for_import(olbooks: list[dict[str, Any]]) -> None:
    """
    For incomplete records, try to stage more complete records from BookWorm.

    This `staged` record is later used to supplement the lacking record once
    the incomplete record is processed via `/api/import`, where additional metadata,
    if found, is merged into the incoming import `rec` from the `staged` record this
    function aims to create.

    An incomplete record lacks one or more of: title, authors, or publish_date.
    See https://github.com/internetarchive/openlibrary/issues/9440.
    """
    total_records = len(olbooks)
    incomplete_records = 0
    timestamp = datetime.datetime.now(datetime.UTC)

    required_fields = ["title", "authors", "publish_date"]
    for book in olbooks:
        # Only look to BookWorm if the current record is incomplete.
        if all(book.get(field) for field in required_fields):
            continue

        incomplete_records += 1

        # Prefer ISBN 13 as an identifier.
        isbn_10 = safeget(lambda: book.get("isbn_10", [])[0])
        isbn_13 = safeget(lambda: book.get("isbn_13", [])[0])
        identifier = to_isbn_13(isbn_13 or isbn_10 or "")

        # Fall back to B* ASIN as a last resort.
        if not identifier:
            if not (amazon := book.get('identifiers', {}).get('amazon', [])):
                continue

            identifier = amazon[0]

        try:
            stage_bookworm_metadata(identifier=identifier)

        except requests.exceptions.ConnectionError:
            logger.exception("Affiliate Server unreachable")
            continue

    # Record promise item completeness rate over time.
    stats.gauge(f"ol.imports.bwb.{timestamp}.total_records", total_records)
    stats.gauge(f"ol.imports.bwb.{timestamp}.incomplete_records", incomplete_records)


def batch_import(promise_id, batch_size=1000, dry_run=False):
    url = "https://archive.org/download/"
    date = promise_id.split("_")[-1]
    resp = requests.get(f"{url}{promise_id}/DailyPallets__{date}.json", stream=True)
    olbooks_gen = (
        map_book_to_olbook(book, promise_id) for book in ijson.items(resp.raw, 'item')
    )

    # Note: dry_run won't include BookWorm data.
    if dry_run:
        for book in olbooks_gen:
            print(json.dumps(book), flush=True)
        return

    olbooks = list(olbooks_gen)

    # Stage incomplete records for import so as to supplement their metadata via
    # `load()`. See https://github.com/internetarchive/openlibrary/issues/9440.
    stage_incomplete_records_for_import(olbooks)

    batch = Batch.find(promise_id) or Batch.new(promise_id)
    batch_items = [{'ia_id': b['local_id'][0], 'data': b} for b in olbooks]
    for i in range(0, len(batch_items), batch_size):
        batch.add_items(batch_items[i : i + batch_size])


def get_promise_items_url(start_date: str, end_date: str):
    """
    >>> get_promise_items_url('2022-12-01', '2022-12-31')
    'https://archive.org/advancedsearch.php?q=collection:bookdonationsfrombetterworldbooks+identifier:bwb_daily_pallets_*+publicdate:[2022-12-01+TO+2022-12-31]&sort=addeddate+desc&fl=identifier&rows=5000&output=json'

    >>> get_promise_items_url('2022-12-01', '2022-12-01')
    'https://archive.org/advancedsearch.php?q=collection:bookdonationsfrombetterworldbooks+identifier:bwb_daily_pallets_*&sort=addeddate+desc&fl=identifier&rows=5000&output=json'

    >>> get_promise_items_url('2022-12-01', '*')
    'https://archive.org/advancedsearch.php?q=collection:bookdonationsfrombetterworldbooks+identifier:bwb_daily_pallets_*+publicdate:[2022-12-01+TO+*]&sort=addeddate+desc&fl=identifier&rows=5000&output=json'
    """
    is_exact_date = start_date == end_date
    selector = start_date if is_exact_date else '*'
    q = f"collection:bookdonationsfrombetterworldbooks identifier:bwb_daily_pallets_{selector}"
    if not is_exact_date:
        q += f' publicdate:[{start_date} TO {end_date}]'

    return "https://archive.org/advancedsearch.php?" + urlencode(
        {
            'q': q,
            'sort': 'addeddate desc',
            'fl': 'identifier',
            'rows': '5000',
            'output': 'json',
        }
    )


def main(ol_config: str, dates: str, dry_run: bool = False):
    """
    :param ol_config: Path to openlibrary.yml
    :param dates: Get all promise items for this date or date range.
        E.g. "yyyy-mm-dd:yyyy-mm-dd" or just "yyyy-mm-dd" for a single date.
        "yyyy-mm-dd:*" for all dates after a certain date.
    """
    if ':' in dates:
        start_date, end_date = dates.split(':')
    else:
        start_date = end_date = dates

    url = get_promise_items_url(start_date, end_date)
    r = requests.get(url)
    identifiers = [d['identifier'] for d in r.json()['response']['docs']]

    if not identifiers:
        logger.info("No promise items found for date(s) %s", dates)
        return

    if not dry_run:
        load_config(ol_config)

    for promise_id in identifiers:
        if dry_run:
            print([promise_id, dry_run], flush=True)
        batch_import(promise_id, dry_run=dry_run)


if __name__ == '__main__':
    FnToCLI(main).run()
