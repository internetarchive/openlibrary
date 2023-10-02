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
import requests
import logging

import _init_path  # Imported for its side effect of setting PYTHONPATH
from infogami import config
from openlibrary.config import load_config
from openlibrary.core.imports import Batch
from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI


logger = logging.getLogger("openlibrary.importer.promises")


def format_date(date: str, only_year: bool) -> str:
    """
    Format date as "yyyy-mm-dd" or only "yyyy"

    :param date: Date in "yyyymmdd" format.
    """
    return date[:4] if only_year else f"{date[0:4]}-{date[4:6]}-{date[6:8]}"


def map_book_to_olbook(book, promise_id):
    asin_is_isbn_10 = book.get('ASIN') and book.get('ASIN')[0].isdigit()
    publish_date = book['ProductJSON'].get('PublicationDate')
    title = book['ProductJSON'].get('Title')
    isbn = book.get('ISBN') or ' '
    sku = book['BookSKUB'] or book['BookSKU'] or book['BookBarcode']
    olbook = {
        'local_id': [f"urn:bwbsku:{sku}"],
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
        'source_records': [f"promise:{promise_id}:{sku}"],
        # format_date adds hyphens between YYYY-MM-DD, or use only YYYY if date is suspect.
        'publish_date': format_date(
            date=publish_date, only_year=publish_date[-4:] in ('0000', '0101')
        )
        if publish_date
        else '????',
    }
    if not olbook['identifiers']:
        del olbook['identifiers']
    return olbook


def batch_import(promise_id, batch_size=1000):
    url = "https://archive.org/download/"
    date = promise_id.split("_")[-1]
    books = requests.get(f"{url}{promise_id}/DailyPallets__{date}.json").json()
    batch = Batch.find(promise_id) or Batch.new(promise_id)
    olbooks = [map_book_to_olbook(book, promise_id) for book in books]
    batch_items = [{'ia_id': b['local_id'][0], 'data': b} for b in olbooks]
    for i in range(0, len(batch_items), batch_size):
        batch.add_items(batch_items[i : i + batch_size])


def get_promise_items(**kwargs):
    url = get_promise_items_url(**kwargs)
    r = requests.get(url)
    return [d['identifier'] for d in r.json()['response']['docs']]


def get_promise_items_url(
    start_date='1996-01-01', end_date="9999-01-01", exact_date=None
):
    base = "https://archive.org/advancedsearch.php"
    selector = exact_date or '*'
    q = f"collection:bookdonationsfrombetterworldbooks+identifier:bwb_daily_pallets_{selector}"
    if not exact_date:
        q += f'+publicdate:[{start_date or "1996-01-01"} TO {end_date}]'
    sorts = "sort%5B%5D=addeddate+desc&sort%5B%5D=&sort%5B%5D="
    fields = "fl%5B%5D=identifier"
    rows = 5000
    url = f"{base}?q={q}&{fields}&{sorts}&rows={rows}&page=1&output=json"
    return url


def parse_date(date: str = ''):
    params = {}
    if ':' in date:
        if date.endswith(':'):
            params['exact_date'] = date[1:-1]
        elif date.startswith(":"):
            params['end_date'] = date[1:]
        else:
            params['start_date'], params['end_date'] = date.split(':')
    elif date:
        params['start_date'] = date
    return params


def main(ol_config: str, date: str):
    """
    start_date
    :end_date
    start_date:end_date
    :exact_date:
    """
    load_config(ol_config)
    params = parse_date(date)
    promise_ids = get_promise_items(**params)
    for i, promise_id in enumerate(promise_ids):
        batch_import(promise_id)


if __name__ == '__main__':
    FnToCLI(main).run()
