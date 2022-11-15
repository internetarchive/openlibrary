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
    olbook = {
        'local_id': [f"urn:bwbsku:{book['BookSKUB']}"],
        'identifiers': {
            **({'amazon': [book.get('ASIN')]} if not asin_is_isbn_10 else {}),
            **(
                {'better_world_books': [book.get('ISBN')]}
                if not book.get('ISBN', ' ')[0].isdigit()
                else {}
            ),
        },
        **(
            {'isbn_13': [book.get('ISBN')]}
            if book.get('ISBN', ' ')[0].isdigit()
            else {}
        ),
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


def get_promise_items():
    url = "https://archive.org/advancedsearch.php"
    q = "collection%3Abookdonationsfrombetterworldbooks+identifier%3Abwb_daily_pallets_*"
    sorts = "sort%5B%5D=addeddate+desc&sort%5B%5D=&sort%5B%5D="
    fields = "fl%5B%5D=identifier"
    rows = 5000
    r = requests.get(f"{url}?q={q}&{fields}&{sorts}&rows={rows}&page=1&output=json")
    return [d['identifier'] for d in r.json()['response']['docs']]


def main(ol_config: str):
    load_config(ol_config)
    promise_ids = get_promise_items()
    for i, promise_id in enumerate(promise_ids):
        batch_import(promise_id)
        if i > 25:
            return  # XXX stop after last 25


if __name__ == '__main__':
    FnToCLI(main).run()
