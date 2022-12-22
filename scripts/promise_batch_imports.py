"""
As of 2022-12: Run on `ol-home0 cron container as

```
$ ssh -A ol-home0
$ docker exec -it -uopenlibrary openlibrary_cron-jobs_1 bash
$ PYTHONPATH="/openlibrary" python3 /openlibrary/scripts/promise_batch_imports.py /olsystem/etc/openlibrary.yml
```

The imports can be monitored for their statuses and rolled up / counted using this query on `ol-db1`:

```
=# select count(*) from import_item where batch_id in (select id from import_batch where name like 'bwb_daily_pallets_%');
```
"""

from __future__ import annotations
import requests
import logging

from infogami import config  # noqa: F401
from openlibrary.config import load_config
from openlibrary.core.imports import Batch
from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI

logger = logging.getLogger("openlibrary.importer.promises")


def format_date(date: str) -> str:
    y = date[0:4]
    m = date[4:6]
    d = date[6:8]
    return f"{y}-{m}-{d}"


def map_book_to_olbook(book, promise_id):
    asin_is_isbn_10 = book.get('ASIN') and book.get('ASIN')[0].isdigit()
    publish_date = book['ProductJSON'].get('PublicationDate')
    title = book['ProductJSON'].get('Title')
    isbn = book.get('ISBN') or ' '
    olbook = {
        'local_id': [f"urn:bwbsku:{book['BookSKUB']}"],
        'identifiers': {
            **({'amazon': [book.get('ASIN')]} if not asin_is_isbn_10 else {}),
            **(
                {'better_world_books': [isbn]}
                if not (isbn and isbn[0].isdigit())
                else {}
            ),
        },
        **({'isbn_13': [isbn]} if (isbn and isbn[0].isdigit()) else {}),
        **({'isbn_10': [book.get('ASIN')]} if asin_is_isbn_10 else {}),
        **({'title': title} if title else {}),
        'authors': [{"name": book['ProductJSON'].get('Author') or '????'}],
        'publishers': [book['ProductJSON'].get('Publisher') or '????'],
        'source_records': [f"promise:{promise_id}"],
        # format_date adds hyphens between YYYY-MM-DD
        'publish_date': publish_date and format_date(publish_date) or '????',
    }
    if not olbook['identifiers']:
        del olbook['identifiers']
    return olbook


def batch_import(promise_id):
    url = "https://archive.org/download/"
    date = promise_id.split("_")[-1]
    books = requests.get(f"{url}{promise_id}/DailyPallets__{date}.json").json()
    batch = Batch.find(promise_id) or Batch.new(promise_id)
    olbooks = [map_book_to_olbook(book, promise_id) for book in books]
    batch_items = [{'ia_id': b['local_id'][0], 'data': b} for b in olbooks]
    batch.add_items(batch_items)


def get_promise_items(start_date=None, end_date="9999-01-01"):
    url = get_promise_items_url(start_date=start_date, end_date=end_date)
    r = requests.get(url)
    return [d['identifier'] for d in r.json()['response']['docs']]


def get_promise_items_url(start_date=None, end_date="9999-01-01"):
    base = "https://archive.org/advancedsearch.php"
    q = "collection%3Abookdonationsfrombetterworldbooks+identifier%3Abwb_daily_pallets_*"
    if start_date:
        q += f"+publicdate%3A[{start_date} TO {end_date}]"
    sorts = "sort%5B%5D=addeddate+desc&sort%5B%5D=&sort%5B%5D="
    fields = "fl%5B%5D=identifier"
    rows = 5000
    url = f"{base}?q={q}&{fields}&{sorts}&rows={rows}&page=1&output=json"
    return url


def main(ol_config: str, start_date: str):
    load_config(ol_config)
    promise_ids = get_promise_items(start_date=start_date)
    for i, promise_id in enumerate(promise_ids):
        batch_import(promise_id)


if __name__ == '__main__':
    FnToCLI(main).run()
