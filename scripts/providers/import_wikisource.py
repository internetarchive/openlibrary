"""
To Run:

PYTHONPATH=. python ./scripts/providers/import_wikisource.py /olsystem/etc/openlibrary.yml
"""

import logging
import re
import requests
import time

import json

from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse
from collections.abc import Callable

# Using both mwparserfromhell and wikitextparser because the former doesn't have a markup stripper
# and the latter doesn't have a method to get a template prop by key.
import mwparserfromhell as mw
import wikitextparser as wtp
from nameparser import HumanName

# from infogami import config
# from openlibrary.config import load_config
# from openlibrary.core.imports import Batch
from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI

logger = logging.getLogger("openlibrary.importer.wikisource")


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
            # Include as many categories and images per response as possible
            'cllimit': 'max',
            'imlimit': 'max',
            # Infobox data
            'rvprop': 'content',
            'rvslots': 'main',
            # Output
            'format': 'json',
        }
        return update_url_with_params(self.api_base_url, params)
    
    @property
    def api_base_url(self) -> str:
        return f'https://{self.langcode}.wikisource.org/w/api.php'

    @property
    def all_api_category_urls(self) -> list[str]:
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
    def set_publish_date(self, publish_date: str | None) -> None:
        self.publish_date = publish_date

    def set_edition(self, edition: str | None) -> None:
        self.edition = edition

    def add_authors(self, authors: list[str]) -> None:
        existing_fullnames = [author.full_name for author in self.authors]
        incoming_names = [HumanName(a) for a in authors]
        self.authors.extend(
            [a for a in incoming_names if a.full_name not in existing_fullnames]
        )

    def set_description(self, description: str | None) -> None:
        self.description = description

    def add_subjects(self, subjects: list[str]) -> None:
        self.subjects.extend([a for a in subjects if a not in self.subjects])

    def set_cover(self, cover: str | None) -> None:
        self.cover = cover

    def add_categories(self, categories: list[str]) -> None:
        self.categories.extend([a for a in categories if a not in self.categories])

    def set_imagename(self, imagename: str | None) -> None:
        self.imagename = imagename

    @property
    def wikisource_id(self) -> str:
        return f'{self.language.langcode}:{self.title.replace(" ", "_")}'

    @property
    def source_records(self) -> list[str]:
        return [f'wikisource:{self.wikisource_id}']

    @staticmethod
    def _format_author(name: HumanName) -> str:
        ln = name.last
        suf = f' {name.suffix}' if name.suffix != "" else ""
        ti = f'{name.title} ' if name.title != "" else ""
        fn = name.first
        mid = f' {name.middle}' if name.middle != "" else ""
        return f"{ln}{suf}, {ti}{fn}{mid}"

    def __init__(
        self,
        title: str,
        language: LangConfig,
        publish_date: str | None = None,
        edition: str | None = None,
        authors: list[str] | None = None,
        description: str | None = None,
        subjects: list[str] | None = None,
        cover: str | None = None,
        categories: list[str] | None = None,
        imagename: str | None = None,
    ):
        self.authors: list[HumanName] = []
        self.categories: list[str] = []
        self.subjects: list[str] = []
        self.title = title
        self.language = language
        self.set_publish_date(publish_date)
        self.set_edition(edition)
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
        output = {
            "title": self.title,
            "source_records": self.source_records,
            "identifiers": {"wikisource": [self.wikisource_id]},
            "languages": [self.language.ol_langcode],
        }
        if self.publish_date is not None:
            output["publish_date"] = self.publish_date
        if self.edition is not None:
            output["edition_name"] = self.edition
        if len(self.authors) > 0:
            output["authors"] = (
                [
                    {
                        "name": BookRecord._format_author(author),
                        "personal_name": BookRecord._format_author(author),
                    }
                    for author in self.authors
                ],
            )
        if self.description is not None:
            output["description"] = self.description
        if len(self.subjects) > 0:
            output["subjects"] = self.subjects
        if self.cover is not None:
            output["cover"] = self.cover
        return output


def update_record(book: BookRecord, new_data: dict, image_titles: list[str]):
    if "categories" in new_data:
        book.add_categories([cat["title"] for cat in new_data["categories"]])

    if book.imagename is None and "images" in new_data:
        # Ignore svgs, these are wikisource photos and other assets that aren't properties of the book.
        linked_images = [
            i
            for i in new_data['images']
            if not i["title"].endswith(".svg") and i["title"] != ""
        ]
        # Set this as the book's image name, which will be used later use its URL in the import
        if len(linked_images) > 0:
            imagename = linked_images[0]["title"]
            book.set_imagename(imagename)
            # Add it to image_titles in order to look up its URL later
            if imagename not in image_titles:
                image_titles.append(imagename)

    # Parse other params from the infobox
    # Exit if infobox doesn't exist
    if not ("revisions" in new_data and len(new_data["revisions"]) > 0):
        return
    infobox = next(
        (
            d["slots"]["main"]["*"]
            for d in new_data["revisions"]
            if "slots" in d and "main" in d["slots"] and "*" in d["slots"]["main"]
        ),
        None,
    )
    if infobox is None:
        return
    wikicode = mw.parse(infobox)
    templates = wikicode.filter_templates()
    if templates is None or len(templates) == 0:
        return
    template = next(
        (template for template in templates if template.name.strip() == "header"), None
    )
    if template is None:
        return

    # If infobox DOES exist, extract book data from it. These are in try-catches.
    # I didn't see a method for the MW parser that checks if a key exists or not
    # instead of throwing an error if it doesn't.
    # Infobox params do not change from language to language as far as I can tell.
    # i.e. "year" will always be "year".

    if book.publish_date is None:
        try:
            yr = template.get("year").value.strip()
            match = re.search(r'\d{4}', yr)
            if match:
                book.set_publish_date(match.group(0))
        except ValueError:
            pass

    # Commenting this out until I can think of a better way to get edition info.
    # The infobox, so far, only ever has "edition": "yes".
    #
    # if book.edition is None:
    #     try:
    #         edition = template.get("edition").value.strip()
    #         if edition != "":
    #             book.set_edition(edition)
    #     except ValueError:
    #         pass

    try:
        author = template.get("author").value.strip()
        if author != "":
            authors = re.split(r'(?:\sand\s|,\s?)', author)
            if len(authors) > 0:
                book.add_authors(authors)
    except ValueError:
        pass

    if book.description is None:
        try:
            # Replace HTML and markup newlines with \n, because they get stripped otherwise
            raw = template.get("notes").value.strip()
            raw_spaced = re.sub(r'(:?<br/>|\{\{rule\}\})', "\n", raw)
            notes = wtp.remove_markup(raw_spaced)
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
    image_titles: list[str] = []

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
                        title=page["title"],
                        language=cfg,
                    )

                # MediaWiki's API paginates through pages, page categories, and page images separately.
                # This means that when you hit this API requesting all 3 of these data types,
                # sequential paginated API responses might contain the same Wikisource book entries, but with different subsets of its properties.
                # i.e. Page 1 might give you a book and its categories, Page 2 might give you the same book and its image info.
                update_record(imports[id], page, image_titles)

            # Proceed to next page of API results
            if 'continue' in data:
                cont_url = update_url_with_params(url, data["continue"])
            else:
                break

    if len(image_titles) > 0:
        # The API calls from earlier that retrieved page data isn't able to return image URLs. 
        # The "imageinfo" prop, which contains URLs, does nothing unless you're querying image names directly.
        # Here we'll query as many images as possible in one API request, build a map of the results,
        # and then later, each valid book will find its image URL in this map to import as its cover.
        image_map: dict[str, str] = {}

        # API will only allow up to 50 images at a time to be requested, so do this in chunks.
        for index in range(0, len(image_titles), 50):
            end = index + 50
            if end > len(image_titles):
                end = len(image_titles)

            image_api_url = update_url_with_params(
                cfg.api_base_url,
                {
                    "action": "query",
                    # Query up to 50 specific image filenames
                    "titles": "|".join(image_titles[index:end]),
                    # Return info about images
                    "prop": "imageinfo",
                    # Specifically, return URL info about images
                    "iiprop": "url",
                    # Output format
                    "format": "json",
                },
            )

            working_url = image_api_url

            # Paginate through results and build the image filename <-> url map
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
                        image_hit = results[id]
                        if (
                            "imageinfo" in image_hit
                            and image_hit["title"] not in image_map
                            and len(image_hit["imageinfo"]) > 0
                            and "url" in image_hit["imageinfo"][0]
                        ):
                            image_map[image_hit["title"]] = image_hit["imageinfo"][0]["url"]

                    # next page of image hits, if necessary
                    if 'continue' in data:
                        working_url = update_url_with_params(
                            image_api_url, data["continue"]
                        )
                    else:
                        break

    # Add all valid books to the batch
    for id in imports:
        book = imports[id]
        # Skip if it belongs to an ignored category, such as subpages (chapters)
        excluded_categories = [
            c for c in book.categories if c in cfg.excluded_categories
        ]
        if len(excluded_categories) > 0:
            continue
        # Set the cover image URL, and then add to batch
        if book.imagename is not None and book.imagename in image_map:
            book.set_cover(image_map[book.imagename])
        batch.append(book)

    if len(batch) > 0:
        output_func(batch)


# If we want to process all Wikisource pages in more than one category, we have to do one API call per category per language.
def process_all_books(cfg: LangConfig, output_func: Callable):
    for url in cfg.all_api_category_urls:
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
    r = [{'ia_id': r.source_records[0], 'data': r.to_dict()} for r in records]
    file_path = f'scripts/providers/batch_output/wikisource-batch-{time.time()}.jsonl'
    with open(file_path, 'w') as file:
        for rec in records:
            r = {'ia_id': rec.source_records[0], 'data': rec.to_dict()}
            file.write(json.dumps(r) + '\n')


def main(ol_config: str, dry_run=False):
    """
    :param str ol_config: Path to openlibrary.yml file
    :param bool dry_run: If true, only print out records to import
    """
    # load_config(ol_config)

    for ws_language in ws_languages:
        if not dry_run:
            process_all_books(ws_language, create_batch)
        else:
            process_all_books(ws_language, print_records)


if __name__ == '__main__':
    FnToCLI(main).run()
