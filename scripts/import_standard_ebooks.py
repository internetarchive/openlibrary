from __future__ import annotations

import json
import requests
import sys
import time

import os.path as path

import feedparser

from openlibrary.core.imports import Batch

sys.path.insert(0, path.abspath(path.join(path.sep, 'openlibrary')))
from openlibrary.config import load_config  # noqa: E402
load_config(
    path.abspath(path.join(
        path.sep, 'olsystem', 'etc', 'openlibrary.yml')))
from infogami import config  # noqa: E402,F401

FEED_URL = 'https://standardebooks.org/opds/all'
LAST_UPDATED_TIME = './out/standard_ebooks_last_updated.txt'


def get_feed():
    """Fetches and returns Standard Ebook's feed."""
    r = requests.get(FEED_URL)
    return feedparser.parse(r.text)


def map_data(entry) -> dict:
    """Maps Standard Ebooks feed entry to an Open Library import object."""
    std_ebooks_id = entry.id.replace('https://standardebooks.org/ebooks/', '')
    return {
        "title": entry.title,
        "source_records": [f"standardebooks:{std_ebooks_id}"],
        "publishers": [entry.publisher],
        "publish_date": entry.dc_issued[0:4],
        "authors": [{"name": author.name} for author in entry.authors],
        "description": entry.content[0].value,
        "subjects": [tag.term for tag in entry.tags],
        "identifiers": {
            "standard_ebooks": [std_ebooks_id]
        }
    }


def create_batch(records: list[dict[str, str]]) -> None:
    """Creates Standard Ebook batch import job.

    Attempts to find existing Standard Ebooks import batch.
    If nothing is found, a new batch is created. All of the
    given import records are added to the batch job as JSON strings.
    """
    now = time.gmtime(time.time())
    batch_name = f'standardebooks-{now.tm_year}{now.tm_mon}'
    batch = Batch.find(batch_name) or Batch.new(batch_name)
    batch.add_items([{
        'ia_id': r['source_records'][0],
        'data': json.dumps(r)} for r in records]
    )


def get_last_updated_time() -> str | None:
    """Gets date of last import job.

    Last updated dates are read from a local file.  If no
    file exists, None is returned. Last updated date is
    expected to be in HTTP-date format:
    https://httpwg.org/specs/rfc7231.html#http.date

    returns last updated date string or None
    """
    if path.exists(LAST_UPDATED_TIME):
        with open(LAST_UPDATED_TIME) as f:
            return f.readline()

    return None


def find_last_updated() -> str | None:
    """Fetches and returns Standard Ebooks most recent update date.

    Returns None if the last modified date is not included in the
    response headers.
    """
    r = requests.head(FEED_URL)
    return r.headers['last-modified'] if r.ok else None


def convert_date_string(date_string: str | None) -> time.struct_time:
    """Converts HTTP-date format string into a struct_time object.

    The date_string will be formatted similarly to this:
    Fri, 05 Nov 2021 03:50:24 GMT

    returns struct_time representation of the given time, or the
    epoch if no time given.

    >>> str(convert_date_string(None)) # doctest: +NORMALIZE_WHITESPACE
    'time.struct_time(tm_year=1970, tm_mon=1, tm_mday=1, tm_hour=0,
        tm_min=0, tm_sec=0, tm_wday=3, tm_yday=1, tm_isdst=0)'

    >>> convert_date_string("") # doctest: +ELLIPSIS
    time.struct_time(tm_year=1970, tm_mon=1, tm_mday=1, tm_hour=0, ...

    >>> convert_date_string(0) # doctest: +ELLIPSIS
    time.struct_time(tm_year=1970, tm_mon=1, tm_mday=1, tm_hour=0, ...

    >>> convert_date_string("Fri, 05 Nov 2021 03:50:24 GMT") # doctest: +ELLIPSIS
    time.struct_time(tm_year=2021, tm_mon=11, tm_mday=5, tm_hour=3, tm_min=50, ...
    """
    if not date_string:
        return time.gmtime(0)
    return time.strptime(date_string[5:-4], '%d %b %Y %H:%M:%S')


def map_entries(
    entries,
    modified_since: time.struct_time
):
    """Returns a list of import objects."""
    return [map_data(e) for e in entries if e.updated_parsed > modified_since]


def import_job() -> None:
    # Make HEAD request to get last-modified time
    last_modified = find_last_updated()

    if not last_modified:
        print(f'HEAD request to {FEED_URL} failed. Not attempting GET request.')
        return

    print(f'Last-Modified date: {last_modified}')

    updated_on = get_last_updated_time()
    if last_modified == updated_on:
        print(f'No new updates since {updated_on}. Processing completed.')
        return

    print(f'Last import job: {updated_on or "No date found"}')
    # Get feed:
    d = get_feed()

    # Create datetime using updated_on:
    modified_since = convert_date_string(updated_on)

    # Map feed entries to list of import objects:
    print(f'Importing all entries that have been updated since {modified_since}.')
    mapped_entries = map_entries(d.entries, modified_since)
    print(f'{len(mapped_entries)} import objects created.')

    # Import all data:
    create_batch(mapped_entries)
    print(f'{len(mapped_entries)} entries added to the batch import job.')

    # Store timestamp for header
    with open(LAST_UPDATED_TIME, 'w') as f:
        f.write(last_modified)
        print(f'Last updated timestamp written to: {LAST_UPDATED_TIME}')


if __name__ == '__main__':
    print("Start: Standard Ebooks import job")
    import_job()
    print("End: Standard Ebooks import job")
