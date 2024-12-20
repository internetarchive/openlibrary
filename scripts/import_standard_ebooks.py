#!/usr/bin/env python
import json
import time
from typing import Any

import feedparser
import requests
from requests.auth import AuthBase, HTTPBasicAuth

from infogami import config
from openlibrary.config import load_config
from openlibrary.core.imports import Batch
from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI

FEED_URL = 'https://standardebooks.org/opds/all'
IMAGE_REL = 'http://opds-spec.org/image'


def get_feed(auth: AuthBase):
    """Fetches and returns Standard Ebook's feed."""
    with requests.get(FEED_URL, auth=auth, stream=True) as r:
        r.raise_for_status()
        return feedparser.parse(r.raw, response_headers=r.headers)


def map_data(entry: dict) -> dict[str, Any]:
    """Maps Standard Ebooks feed entry to an Open Library import object."""
    std_ebooks_id = entry['id'].replace('https://standardebooks.org/ebooks/', '')

    # Standard ebooks only has English works at this time ; because we don't have an
    # easy way to translate the language codes they store in the feed to the MARC
    # language codes, we're just gonna handle English for now, and have it error
    # if Standard Ebooks ever adds non-English works.
    lang = entry.get('dcterms_language')
    if not lang or not lang.startswith('en-'):
        raise ValueError(f'Feed entry language {lang} is not supported.')
    import_record = {
        "title": entry['title'],
        "source_records": [f"standard_ebooks:{std_ebooks_id}"],
        "publishers": ['Standard Ebooks'],
        "publish_date": entry['published'][0:4],
        "authors": [{"name": author['name']} for author in entry['authors']],
        "description": entry['content'][0]['value'],
        "subjects": [tag['term'] for tag in entry['tags']],
        "identifiers": {"standard_ebooks": [std_ebooks_id]},
        "languages": ['eng'],
    }

    cover_url = next(
        (link['href'] for link in entry['links'] if link['rel'] == IMAGE_REL),
        None,
    )
    if cover_url:
        # This used to be a relative URL; ensure the API doesn't change.
        assert cover_url.startswith('https://')
        import_record['cover'] = cover_url

    return import_record


def create_batch(records: list[dict[str, str]]) -> None:
    """Creates Standard Ebook batch import job.

    Attempts to find existing Standard Ebooks import batch.
    If nothing is found, a new batch is created. All of the
    given import records are added to the batch job as JSON strings.
    """
    now = time.gmtime(time.time())
    batch_name = f'standardebooks-{now.tm_year}{now.tm_mon}'
    batch = Batch.find(batch_name) or Batch.new(batch_name)
    batch.add_items([{'ia_id': r['source_records'][0], 'data': r} for r in records])


def import_job(
    ol_config: str,
    dry_run: bool = False,
) -> None:
    """
    :param str ol_config: Path to openlibrary.yml file
    :param bool dry_run: If true, only print out records to import
    """
    load_config(ol_config)

    if not config.get('standard_ebooks_key'):
        print('Standard Ebooks key not found in config. Exiting.')
        return

    auth = HTTPBasicAuth(config.get('standard_ebooks_key'), '')
    feed = map(map_data, get_feed(auth).entries)

    if not dry_run:
        list_feed = list(feed)
        create_batch(list_feed)
        print(f'{len(list_feed)} entries added to the batch import job.')
    else:
        for record in feed:
            print(json.dumps(record))


if __name__ == '__main__':
    print("Start: Standard Ebooks import job")
    FnToCLI(import_job).run()
    print("End: Standard Ebooks import job")
