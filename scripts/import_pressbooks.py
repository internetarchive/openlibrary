"""
To run:

PYTHONPATH=. python ./scripts/import_pressbooks.py /olsystem/etc/openlibrary.yml ./path/to/pressbooks.json
"""

import json
import datetime
import logging
import requests
import html

from infogami import config  # noqa: F401
from openlibrary.config import load_config
from openlibrary.core.imports import Batch
from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI

logger = logging.getLogger("openlibrary.importer.pressbooks")


langs = {
    lang['identifiers']['iso_639_1'][0]: lang['code']
    for lang in requests.get(
        'https://openlibrary.org/query.json',
        {
            'limit': '500',
            'type': '/type/language',
            'identifiers.iso_639_1~': '*',
            'identifiers': '',
            'code': '',
        },
    ).json()
}


def convert_pressbooks_to_ol(data):
    book = {"source_records": ['pressbooks:%s' % data['url']]}
    if data.get('isbn'):
        book['isbn_13'] = [
            isbn.split(' ')[0].replace('-', '') for isbn in data['isbn'].split('; ')
        ]
    if data.get('name'):
        book['title'] = html.unescape(data['name'])
    if data.get('languageCode'):
        book['languages'] = [langs[data['languageCode'].split('-', 1)[0]]]
    if data.get('author'):
        book['authors'] = [{"name": a} for a in data.get('author')]
    if data.get('image') and not data['image'].endswith('default-book-cover.jpg'):
        book['cover'] = data['image']
    description = (
        (data.get('description') or '')
        + '\n\n'
        + (data.get('disambiguatingDescription') or '')
    ).strip()
    if description:
        book['description'] = description
    if data.get('alternateName'):
        book['other_titles'] = [data['alternateName']]
    if data.get('alternativeHeadline'):
        book['edition_name'] = data['alternativeHeadline']
    book['publish_date'] = (
        data.get('datePublished')
        or data.get('copyrightYear')
        or datetime.datetime.fromtimestamp(data.get('lastUpdated')).date().isoformat()
    )
    assert book['publish_date'], data

    subjects = (data.get('about') or []) + (data.get('keywords') or '').split(', ')
    if subjects:
        book['subjects'] = [
            s.strip().capitalize() for s in subjects if s  # Sometimes they're null?
        ]

    book['publishers'] = [p for p in (data.get('networkName'), "Pressbooks") if p]

    book['providers'] = [
        {
            'provider': 'pressbooks',
            'url': data['url'],
        }
    ]
    book['physical_format'] = 'Ebook'

    copyright_line = ' '.join(
        [
            data.get('copyrightYear') or '',
            data.get('copyrightHolderName') or '',
        ]
    ).strip()
    if copyright_line:
        book['copyright_date'] = copyright_line

    if data.get('wordCount'):
        book['word_count'] = data['wordCount']

    contributors_map = {
        'translator': 'Translator',
        'editor': 'Editor',
        'illustrator': 'Illustrator',
        'reviewedBy': 'Reviewer',
        'contributor': 'Contributor',
    }

    contributors = [
        [
            {"name": person, "role": ol_role}
            for person in (data.get(pressbooks_field) or [])
        ]
        for pressbooks_field, ol_role in contributors_map.items()
    ]
    contributors = [contributor for lst in contributors if lst for contributor in lst]

    if contributors:
        book['contributors'] = contributors

    return book


def main(ol_config: str, filename: str, batch_size=5000, dry_run=False):

    if not dry_run:
        load_config(ol_config)
        date = datetime.date.today()
        batch_name = f"pressbooks-{date:%Y%m}"
        batch = Batch.find(batch_name) or Batch.new(batch_name)

    with open(filename, 'rb') as f:
        book_items = []
        books = json.load(f)
        for line_num, record in enumerate(books):
            # try:
            b = convert_pressbooks_to_ol(record)
            book_items.append({'ia_id': b['source_records'][0], 'data': b})
            # except (AssertionError, IndexError) as e:
            #    logger.info(f"Error: {e} from {line}")

            if dry_run:
                print(json.dumps(b))
            # If we have enough items, submit a batch
            elif not ((line_num + 1) % batch_size):
                batch.add_items(book_items)
                book_items = []  # clear added items

        # Add any remaining book_items to batch
        if not dry_run and book_items:
            batch.add_items(book_items)


if __name__ == '__main__':
    FnToCLI(main).run()
