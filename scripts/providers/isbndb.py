import json
import logging
import os
import re
from json import JSONDecodeError
from typing import Any, Final

import requests

from openlibrary.config import load_config
from openlibrary.core.imports import Batch
from openlibrary.plugins.upstream.utils import get_marc21_language
from scripts.partner_batch_imports import is_published_in_future_year
from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI

logger = logging.getLogger("openlibrary.importer.isbndb")

SCHEMA_URL = (
    "https://raw.githubusercontent.com/internetarchive"
    "/openlibrary-client/master/olclient/schemata/import.schema.json"
)

NONBOOK: Final = ['dvd', 'dvd-rom', 'cd', 'cd-rom', 'cassette', 'sheet music', 'audio']
RE_YEAR = re.compile(r'(\d{4})')


def is_nonbook(binding: str, nonbooks: list[str]) -> bool:
    """
    Determine whether binding, or a substring of binding, split on " ", is
    contained within nonbooks.
    """
    words = binding.split(" ")
    return any(word.casefold() in nonbooks for word in words)


class ISBNdb:
    ACTIVE_FIELDS: tuple[str, ...] = (
        'authors',
        'isbn_13',
        'languages',
        'number_of_pages',
        'publish_date',
        'publishers',
        'source_records',
        'subjects',
        'title',
    )
    INACTIVE_FIELDS = (
        "copyright",
        "dewey",
        "doi",
        "height",
        "issn",
        "lccn",
        "length",
        "width",
        'lc_classifications',
        'pagination',
        'weight',
    )
    REQUIRED_FIELDS = requests.get(SCHEMA_URL).json()['required']

    def __init__(self, data: dict[str, Any]):
        self.isbn_13 = [data.get('isbn13')]
        self.source_id = f'idb:{self.isbn_13[0]}'
        self.title = data.get('title')
        self.publish_date = self._get_year(data)  # 'YYYY'
        self.publishers = self._get_list_if_present(data.get('publisher'))
        self.authors = self.contributors(data)
        self.number_of_pages = data.get('pages')
        self.languages = self._get_languages(data)
        self.source_records = [self.source_id]
        self.subjects = [
            subject.capitalize() for subject in (data.get('subjects') or []) if subject
        ]
        self.binding = data.get('binding', '')

        # Assert importable
        for field in self.REQUIRED_FIELDS + ['isbn_13']:
            assert getattr(self, field), field
        assert is_nonbook(self.binding, NONBOOK) is False, "is_nonbook() returned True"
        assert self.isbn_13 != [
            "9780000000002"
        ], f"known bad ISBN: {self.isbn_13}"  # TODO: this should do more than ignore one known-bad ISBN.

    def _get_languages(self, data: dict[str, Any]) -> list[str] | None:
        """Extract a list of MARC 21 format languages from an ISBNDb JSONL line."""
        language_line = data.get('language')
        if not language_line:
            return None

        possible_languages = re.split(',| |;', language_line)
        unique_languages = []

        for language in possible_languages:
            if (
                marc21_language := get_marc21_language(language)
            ) and marc21_language not in unique_languages:
                unique_languages.append(marc21_language)

        return unique_languages or None

    def _get_list_if_present(self, item: str | None) -> list[str] | None:
        """Return items as a list, or None."""
        return [item] if item else None

    def _get_year(self, data: dict[str, Any]) -> str | None:
        """Return a year str/int as a four digit string, or None."""
        result = ""
        if publish_date := data.get('date_published'):
            if isinstance(publish_date, str):
                m = RE_YEAR.search(publish_date)
                result = m.group(1) if m else None  # type: ignore[assignment]
            else:
                result = str(publish_date)[:4]

        return result or None

    def _get_subjects(self, data: dict[str, Any]) -> list[str] | None:
        """Return a list of subjects None."""
        subjects = [
            subject.capitalize() for subject in data.get('subjects', '') if subject
        ]
        return subjects or None

    @staticmethod
    def contributors(data: dict[str, Any]) -> list[dict[str, Any]] | None:
        """Return a list of author-dicts or None."""

        def make_author(name):
            author = {'name': name}
            return author

        if contributors := data.get('authors'):
            # form list of author dicts
            authors = [make_author(c) for c in contributors if c[0]]
            return authors

        return None

    def json(self):
        """Return a JSON representation of the object."""
        return {
            field: getattr(self, field)
            for field in self.ACTIVE_FIELDS
            if getattr(self, field)
        }


def load_state(path: str, logfile: str) -> tuple[list[str], int]:
    """Retrieves starting point from logfile, if log exists

    Takes as input a path which expands to an ordered candidate list
    of isbndb* filenames to process, the location of the
    logfile, and determines which of those files are remaining, as
    well as what our offset is in that file.

    e.g. if we request path containing f1, f2, f3 and our log
    says f2,100 then we start our processing at f2 at the 100th line.

    This assumes the script is being called w/ e.g.:
    /1/var/tmp/imports/2021-08/Bibliographic/*/
    """
    filenames = sorted(
        os.path.join(path, f) for f in os.listdir(path) if f.startswith("isbndb")
    )
    try:
        with open(logfile) as fin:
            active_fname, offset = next(fin).strip().split(',')
            unfinished_filenames = filenames[filenames.index(active_fname) :]
            return unfinished_filenames, int(offset)
    except (ValueError, OSError):
        return filenames, 0


def get_line(line: bytes) -> dict | None:
    """converts a line to a book item"""
    json_object = None
    try:
        json_object = json.loads(line)
    except JSONDecodeError as e:
        logger.info(f"json decoding failed for: {line!r}: {e!r}")

    return json_object


def get_line_as_biblio(line: bytes, status: str) -> dict | None:
    if json_object := get_line(line):
        b = ISBNdb(json_object)
        return {'ia_id': b.source_id, 'status': status, 'data': b.json()}

    return None


def update_state(logfile: str, fname: str, line_num: int = 0) -> None:
    """Records the last file we began processing and the current line"""
    with open(logfile, 'w') as fout:
        fout.write(f'{fname},{line_num}\n')


# TODO: It's possible `batch_import()` could be modified to take a parsing function
# and a filter function instead of hardcoding in `csv_to_ol_json_item()` and some filters.
def batch_import(path: str, batch: Batch, import_status: str, batch_size: int = 5000):
    logfile = os.path.join(path, 'import.log')
    filenames, offset = load_state(path, logfile)

    for fname in filenames:
        book_items = []
        with open(fname, 'rb') as f:
            logger.info(f"Processing: {fname} from line {offset}")
            for line_num, line in enumerate(f):
                # skip over already processed records
                if offset:
                    if offset > line_num:
                        continue
                    offset = 0

                try:
                    book_item = get_line_as_biblio(line=line, status=import_status)
                    assert book_item is not None
                    if not any(
                        [
                            "independently published"
                            in book_item['data'].get('publishers', ''),
                            is_published_in_future_year(book_item["data"]),
                        ]
                    ):
                        book_items.append(book_item)
                except (AssertionError, IndexError) as e:
                    logger.info(f"Error: {e!r} from {line!r}")

                # If we have enough items, submit a batch
                if not ((line_num + 1) % batch_size):
                    batch.add_items(book_items)
                    update_state(logfile, fname, line_num)
                    book_items = []  # clear added items

            # Add any remaining book_items to batch
            if book_items:
                batch.add_items(book_items)
            update_state(logfile, fname, line_num)


def main(ol_config: str, batch_path: str, import_status: str = 'staged') -> None:
    load_config(ol_config)

    # Partner data is offset ~15 days from start of month
    batch_name = "isbndb_bulk_import"
    batch = Batch.find(batch_name) or Batch.new(batch_name)
    batch_import(path=batch_path, batch=batch, import_status=import_status)


if __name__ == '__main__':
    FnToCLI(main).run()
