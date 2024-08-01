"""
To Run:

PYTHONPATH=. python ./scripts/providers/import_wikisource.py /olsystem/etc/openlibrary.yml
"""

import logging
import re
import requests
import time
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse
from typing import Any
from collections.abc import Callable

# Using both mwparserfromhell and wikitextparser because the former doesn't have a markup stripper
# and the latter doesn't have a method to get a template prop by key.
import mwparserfromhell as mw
import wikitextparser as wtp

from infogami import config
from openlibrary.config import load_config
from openlibrary.core.imports import Batch
from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI

logger = logging.getLogger("openlibrary.importer.pressbooks")


def update_url_with_params(url: str, new_params: dict[str, str]):
    url_parts = list(urlparse(url))
    query = dict(parse_qsl(url_parts[4]))
    query.update(new_params)
    url_parts[4] = urlencode(query)
    return urlunparse(url_parts)


class LangConfig:
    def __init__(
        self,
        langcode: str,
        ol_langcode: str,
        category_prefix: str,
        included_categories: list[str],
        excluded_categories: list[str],
    ):
        self.langcode = langcode
        self.ol_langcode = ol_langcode
        self._category_prefix = category_prefix
        self._included_categories = included_categories
        self._excluded_categories = excluded_categories

    def _catformat(self, category: str) -> str:
        return f'{self._category_prefix}:{category}'

    def _api_url(self, category: str) -> str:
        url = f'https://{self.langcode}.wikisource.org/w/api.php'
        params = {
            'action': 'query',
            # Forces the inclusion of category data
            'generator': 'categorymembers',
            # Restrict to only validated texts
            'gcmtitle': self._catformat(category),
            # Max response size allowed by the API
            'gcmlimit': 'max',
            # Relevant page data. The inclusion of |revisions, and rvprop/rvslots, are used to get book info from the page's infobox.
            'prop': 'categories|revisions|images',
            # Includes as many categories per hit as possible
            'cllimit': 'max',
            # Infobox data
            'rvprop': 'content',
            'rvslots': 'main',
            # Output
            'format': 'json',
        }
        return update_url_with_params(url, params)

    @property
    def api_urls(self) -> list[str]:
        return [self._api_url(c) for c in self._included_categories]

    @property
    def excluded_categories(self) -> list[str]:
        return [self._catformat(c) for c in self._excluded_categories]


# Each version of wikisource has different category names and prefixes,
# so the pool of categories to search within and the categories to filter out
# will have different names per wikisource version.
# We need to explicitly exclude irrelevant categories because Wikisource does not have a unique category for books.
# You can add more Wikisource languages here as desired.
ws_languages = [
    LangConfig(
        langcode='en',
        ol_langcode='eng',
        category_prefix='Category',
        included_categories=['Validated_texts'],
        excluded_categories=['Subpages', 'Posters'],
    )
]


class BookRecord:
    def set_publish_date(self, publish_date: str) -> None:
        self.publish_date = publish_date

    def add_authors(self, authors: list[str]) -> None:
        self.authors.extend([a for a in authors if a not in self.authors])

    def set_description(self, description: str) -> None:
        self.description = description

    def add_subjects(self, subjects: list[str]) -> None:
        self.subjects.extend([a for a in subjects if a not in self.subjects])

    def set_cover(self, cover: str) -> None:
        self.cover = cover

    def add_categories(self, categories: list[str]) -> None:
        self.categories.extend([a for a in categories if a not in self.categories])

    def set_imagename(self, imagename: str) -> None:
        self.imagename = imagename

    @property
    def wikisource_id(self) -> str:
        return f'{self.cfg.langcode}:{self.title.replace(" ", "_")}'

    @property
    def source_records(self) -> list[str]:
        return [f'wikisource:{self.wikisource_id}']

    def __init__(
        self,
        title: str,
        cfg: LangConfig,
        publish_date: str = "",
        authors: list[str] = None,
        description: str = "",
        subjects: list[str] = None,
        cover: str = "",
        categories: list[str] = None,
        imagename: str = "",
    ):
        self.authors: list[str] = []
        self.categories: list[str] = []
        self.subjects: list[str] = []
        self.title = title
        self.cfg = cfg
        self.set_publish_date(publish_date)
        if authors is not None:
            self.add_authors(authors)
        self.set_description(description)
        if subjects is not None:
            self.add_subjects(subjects)
        self.set_cover(cover)
        if categories is not None:
            self.add_categories(categories)
        self.set_imagename(imagename)

    def to_dict(self):
        return {
            "title": self.title,
            "source_records": self.source_records,
            "publishers": 'Wikisource',
            "publish_date": self.publish_date,
            "authors": self.authors,
            "description": self.description,
            "subjects": self.subjects,
            "identifiers": {"wikisource": self.wikisource_id},
            "languages": [self.cfg.ol_langcode],
            "cover": self.cover,
        }


def update_record(book: BookRecord, new_data: dict, cfg: LangConfig):
    if "categories" in new_data:
        book.add_categories([cat["title"] for cat in new_data["categories"]])

    if book.imagename == "" and "images" in new_data:
        # Ignore svgs, these are wikisource photos and other assets that aren't properties of the book.
        image_names = [
            i
            for i in new_data['images']
            if not i["title"].endswith(".svg") and i["title"] != ""
        ]
        if len(image_names) > 0:
            book.set_imagename(image_names[0]["title"])

    # Parse other params from the infobox if it exists.
    # Infobox params do not change from language to language as far as I can tell. i.e. "year" will always be "year".
    if (
        "revisions" in new_data
        and len(new_data["revisions"]) > 0
        and "slots" in new_data["revisions"][0]
        and "main" in new_data["revisions"][0]["slots"]
        and "*" in new_data["revisions"][0]["slots"]["main"]
    ):
        infobox = new_data["revisions"][0]["slots"]["main"]["*"]

        wikicode = mw.parse(infobox)
        templates = wikicode.filter_templates()

        # no infobox
        if templates is None or len(templates) == 0:
            return
        template = next(
            (template for template in templates if not isinstance(template, str)), None
        )
        if template is None:
            return

        # Infobox properties are in try-catches.
        # I didn't see a method for the MW parser that checks if a key exists or not instead of throwing an error if it doesn't.
        try:
            yr = template.get("year").value.strip()
            match = re.search(r'\d{4}', yr)
            if match:
                book.set_publish_date(match.group(0))
        except ValueError:
            pass

        try:
            author = template.get("author").value.strip()
            if author != "":
                authors = re.split(r'(?:\sand\s|,\s?)', author)
                if len(authors) > 0:
                    book.add_authors(authors)
        except ValueError:
            pass

        try:
            notes = wtp.remove_markup(template.get("notes").value.strip())
            if notes != "":
                book.set_description(notes)
        except ValueError:
            pass

        try:
            subject: str = template.get("portal").value.strip()
            if subject != "":
                book.add_subjects(subject.split("/"))
        except ValueError:
            pass


def scrape_api(url: str, cfg: LangConfig, output_func: Callable):
    cont_url = url
    imports: dict[str, BookRecord] = {}
    batch: list[BookRecord] = []

    # Paginate through metadata about wikisource pages
    while True:
        with requests.get(cont_url, stream=True) as r:
            r.raise_for_status()
            data = r.json()
            if "query" not in data:
                break
            if "pages" not in data["query"]:
                break
            results = data["query"]["pages"]

            for id in results:
                page = results[id]

                if id not in imports:
                    imports[id] = BookRecord(
                        title=id,
                        cfg=cfg,
                    )

                # MediaWiki's API paginates through pages, page categories, and page images separately.
                # This means that when you hit this API requesting all 3 of these data types,
                # sequential paginated API responses might contain the same Wikisource book entries, but with different subsets of its properties.
                # i.e. Page 1 might give you a book and its categories, Page 2 might give you the same book and its image info.
                update_record(imports[id], page, cfg)

            # Proceed to next page of API results
            if 'continue' in data:
                cont_url = update_url_with_params(url, data["continue"])
            else:
                break

    # The page query can't include image URLs, the "imageinfo" prop does nothing unless you're querying image names directly.
    # Here we'll query as many images as possible in one API request, build a map of the results,
    # and then later, each valid book will find its image URL in this map.
    # Get all unique image filenames
    image_titles: list[str] = []
    for id in imports:
        book = imports[id]
        if book.imagename != "" and book.imagename not in image_titles:
            image_titles.append(book.imagename)

    # Build an image filename<->url map
    image_map: dict[str, str] = {}

    if len(image_titles) > 0:
        # API will only allow up to 50 images at a time to be requested, so do this in chunks.
        for index in range(0, len(image_titles), 50):
            end = index + 50
            if end > len(image_titles):
                end = len(image_titles)

            image_url = update_url_with_params(
                f"https://{cfg.langcode}.wikisource.org/w/api.php",
                {
                    "action": "query",
                    "titles": "|".join(image_titles[index:end]),
                    "prop": "imageinfo",
                    "iiprop": "url",
                    "format": "json",
                },
            )

            working_url = image_url

            # Paginate through results
            while True:
                with requests.get(working_url, stream=True) as r:
                    r.raise_for_status()
                    data = r.json()
                    if "query" not in data:
                        break
                    if "pages" not in data["query"]:
                        break
                    results = data["query"]["pages"]
                    for id in results:
                        img = results[id]
                        if (
                            "imageinfo" in img
                            and img["title"] not in image_map
                            and len(img["imageinfo"]) > 0
                            and "url" in img["imageinfo"][0]
                        ):
                            image_map[img["title"]] = img["imageinfo"][0]["url"]

                    # scrape_api next pagination
                    if 'continue' in data:
                        working_url = update_url_with_params(
                            image_url, data["continue"]
                        )
                    else:
                        break

    # Add all valid books to the batch, and give them their image URLs
    for id in imports:
        book = imports[id]
        # Skip if it belongs to an ignored category, such as subpages (chapters)
        excluded_categories = [
            c for c in book.categories if c in cfg.excluded_categories
        ]
        if len(excluded_categories) > 0:
            continue
        if book.imagename != "" and book.imagename in image_map:
            book.set_cover(image_map[book.imagename])
        batch.append(book)

    print(batch)
    if len(batch) > 0:
        output_func(batch)


# If we want to process all Wikisource pages in more than one category, we have to do one API call per category per language.
def process_all_books(cfg: LangConfig, output_func: Callable):
    for url in cfg.api_urls:
        scrape_api(url, cfg, output_func)


def create_batch(records: list[BookRecord]):
    """Creates Wikisource batch import job.

    Attempts to find existing Wikisource import batch.
    If nothing is found, a new batch is created.
    """
    now = time.gmtime(time.time())
    batch_name = f'wikisource-{now.tm_year}{now.tm_mon}'
    batch = Batch.find(batch_name) or Batch.new(batch_name)
    batch.add_items(
        [{'ia_id': r.source_records[0], 'data': r.to_dict()} for r in records]
    )
    print(f'{len(records)} entries added to the batch import job.')


def print_records(records: list[BookRecord]):
    print([{'ia_id': r.source_records[0], 'data': r.to_dict()} for r in records])


def main(ol_config: str, dry_run=False):
    """
    :param str ol_config: Path to openlibrary.yml file
    :param bool dry_run: If true, only print out records to import
    """
    load_config(ol_config)

    for ws_language in ws_languages:
        if not dry_run:
            process_all_books(ws_language, create_batch)
        else:
            process_all_books(ws_language, print_records)


if __name__ == '__main__':
    FnToCLI(main).run()
