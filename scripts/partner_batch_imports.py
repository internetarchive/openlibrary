"""
Process partner bibliographic csv data into importable json book
records and then batch submit into the ImportBot
`import_item` table (http://openlibrary.org/admin/imports)
which queues items to be imported via the
Open Library JSON import API: https://openlibrary.org/api/import
"""

import os
import re
import sys
import web
import datetime
from datetime import timedelta
import logging
import requests

# Add openlibrary into our path so we can process config + batch functions
from openlibrary.core.imports import Batch
from infogami import config
from openlibrary.config import load_config

logger = logging.getLogger("openlibrary.importer.bwb")

SCHEMA_URL = "https://raw.githubusercontent.com/internetarchive" \
             "/openlibrary-client/master/olclient/schemata/import.schema.json"


class Biblio():

    ACTIVE_FIELDS = [
        'title', 'isbn_13', 'publish_date', 'publishers',
        'weight', 'authors', 'lc_classifications', 'number_of_pages',
        'languages', 'subjects', 'source_records'
    ]
    INACTIVE_FIELDS = [
        "copyright", "issn", "doi", "lccn", "dewey", "length",
        "width", "height"
    ]
    REQUIRED_FIELDS = requests.get(SCHEMA_URL).json()['required']

    def __init__(self, data):
        self.isbn = data[124]
        self.isbn_13 = [self.isbn]
        self.title = data[10]
        self.publish_date = data[20][:4]  # YYYY, YYYYMMDD
        self.publishers = [data[135]]
        self.weight = data[39]
        self.authors = self.contributors(data)
        self.lc_classifications = data[147]
        self.number_of_pages = next(
            # Regex find the first number in data[36] or default None
            iter(re.findall('[0-9]+', data[36])),
            None
        )
        self.languages = [data[37].lower()]
        self.source_records = ['bwb:%s' % self.isbn]
        self.subjects = [
            s.capitalize().replace('_', ', ')
            for s in data[91:100]
            # + data[101:120]
            # + data[153:158]
            if s
        ]

        # Inactive fields
        self.copyright = data[19]
        self.issn = data[54]
        self.doi = data[145]
        self.lccn = data[146]
        self.dewey = data[49]
        # physical_dimensions
        # e.g. "5.4 x 4.7 x 0.2 inches"
        self.length, self.width, self.height = (
            data[40], data[41], data[42]
        )

        # Assert importable
        assert self.isbn_13
        for field in self.REQUIRED_FIELDS:
            assert getattr(self, field)

    @staticmethod
    def contributors(data):
        def make_author(contributor):
            author = {'name': contributor[0]}
            if contributor[2] == 'X':
                # set corporate contributor
                author['entity_type'] = 'org'
            # TODO: sort out contributor types
            # AU = author
            # ED = editor
            return author

        contributors = (
            (data[21+i*3], data[22+i*3], data[23+i*3]) for i in range(5)
        )

        # form list of author dicts
        authors = [make_author(c) for c in contributors if c[0]]
        return authors

    def json(self):
        return dict(
            (field, getattr(self, field))
            for field in self.ACTIVE_FIELDS
            if getattr(self, field)
        )


def load_state(path, logfile):
    """Retrieves starting point from logfile, if log exists

    Takes as input a path which expands to an ordered candidate list
    of bettworldbks* filenames to process, the location of the
    logfile, and determines which of those files are remaining, as
    well as what our offset is in that file.

    e.g. if we request path containing f1, f2, f3 and our log
    says f2,100 then we start our processing at f2 at the 100th line.

    This assumes the script is being called w/ e.g.:
    /1/var/tmp/imports/2021-08/Bibliographic/*/
    """
    filenames = sorted([
        os.path.join(path, f)
        for f in os.listdir(path)
        if f.startswith("bettworldbks")
    ])
    try:
        with open(logfile) as fin:
            active_fname, offset = next(fin).strip().split(',')
            unfinished_filenames = filenames[filenames.index(active_fname):]
            return unfinished_filenames, int(offset)
    except (ValueError, OSError):
        return filenames, 0


def update_state(logfile, fname, line_num=0):
    """Records the last file we began processing and the current line"""
    with open(logfile, 'w') as fout:
        fout.write('%s,%s\n' % (fname, line_num))


def csv_to_ol_json_item(line):
    """converts a line to a book item"""
    b = Biblio(line.strip().split('|'))
    return {
        'ia_id': 'isbn:%s' % b.isbn,
        'data': b.json()
    }


def batch_import(path, batch, batch_size=5000):
    logfile = os.path.join(path, 'import.log')
    filenames, offset = load_state(path, logfile)

    for fname in filenames:
        book_items = []
        with open(fname, 'r', encoding="ISO-8859-1") as f:
            logger.info("Processing: %s from line %s" % (fname, offset))
            for line_num, line in enumerate(f):

                # skip over already processed records
                if offset:
                    if offset > line_num:
                        continue
                    offset = 0

                try:
                    book_items.append(csv_to_ol_json_item(line))
                except UnicodeDecodeError:
                    pass

                # If we have enough items, submit a batch
                if not ((line_num + 1) % batch_size):
                    batch.add_items(book_items)
                    update_state(logfile, fname, line_num)
                    book_items = []  # clear added items

            # Add any remaining book_items to batch
            if book_items:
                batch.add_items(book_items)
            update_state(logfile, fname, line_num)


def main():
    load_config(
        os.path.abspath(os.path.join(
            os.sep, 'olsystem', 'etc', 'openlibrary.yml')))
    # Partner data is offset ~15 days from start of month
    date = datetime.date.today() - timedelta(days=15)
    batch_name = "%s-%04d%02d" % ('bwb', date.year, date.month)
    batch = Batch.find(batch_name) or Batch.new(batch_name)
    batch_import(sys.argv[1], batch)


if __name__ == '__main__':
    main()
