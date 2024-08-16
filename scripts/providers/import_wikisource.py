"""
To Run:

PYTHONPATH=. python ./scripts/providers/import_wikisource.py /olsystem/etc/openlibrary.yml
"""

import logging
import re
import requests
import time
import json
import os

from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse, quote

# Using both mwparserfromhell and wikitextparser because the former doesn't have a markup stripper
# and the latter doesn't have a method to get a template prop by key.
import mwparserfromhell as mw
import wikitextparser as wtp
from nameparser import HumanName

from openlibrary.config import load_config
from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI

logger = logging.getLogger("openlibrary.importer.wikisource")


def update_url_with_params(url: str, new_params: dict[str, str]):
    url_parts = list(urlparse(url))
    query = dict(parse_qsl(url_parts[4]))
    query.update(new_params)
    url_parts[4] = urlencode(query, quote_via=quote)
    return urlunparse(url_parts)


EXCLUDED_WIKIDATA_INSTANCES = [
    "Q386724",  # raw works
    "Q5185279",  # poem
    "Q10870555",  # reports
    "Q49848",  # documents
    "Q47461344",  # written work - this is meant to be a parent class of documents, manuscripts, etc, things that aren't books
    "Q697279",  # petitions
    "Q660651",  # memoranda
    "Q327611",  # flyers
    "Q2085515",  # minutes
    "Q190399",  # pamphlets
    "Q15916459",  # pleas
]

EXCLUDED_WIKIDATA_SUBCLASSES = [
    "Q191067",  # articles
    "Q4502142",  # visual artwork
    "Q1784733",  # correspondences
    "Q35760",  # essays
    "Q6087062",  # legal proceedings
    "Q52943",  # interviews
    "Q814441",  # certifications
    "Q861911",  # orations
    "Q2135540",  # legal actions
    "Q133492",  # letters
    "Q3150005",  # legal instruments
    "Q18120378",  # lab measurements
    "Q1572600",  # proclamations
    "Q820655",  # statutes
    "Q2571972",  # decrees
    "Q253623",  # patents
    "Q108163",  # propositions
    "Q628523",  # messages
    "Q5962346",  # classification scheme
]

EXCLUDED_WIKIDATA_GENRES = [
    "Q603773",  # lectures
    "Q861911",  # orations
    "Q35760",  # essays
    "Q60797",  # sermons
    "Q133492",  # letters
]

WIKIDATA_API_URL = "https://query.wikidata.org/bigdata/namespace/wdq/sparql"


def get_wd_item_id(string: str):
    split_url = string.split("/")
    return split_url[len(split_url) - 1]


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
        return f"{self._category_prefix}:{category}"

    def _sparql_query(self, category: str) -> str:
        return (
            '''SELECT DISTINCT
  ?page
  ?item
WHERE {
  SERVICE wikibase:mwapi {
    bd:serviceParam wikibase:endpoint "'''
            + self.langcode
            + '''.wikisource.org";
                    wikibase:api "Generator";
                    mwapi:generator "categorymembers";
                    mwapi:gcmtitle "'''
            + self._catformat(category)
            + '''".
    ?page wikibase:apiOutput mwapi:title.
    ?item wikibase:apiOutputItem mwapi:item .
  }

  ?item wdt:P31/wdt:P279* ?instanceOf.
  '''
            + ''.join(
                [
                    f"FILTER NOT EXISTS {{ ?item wdt:P31/wdt:P279* wd:{type}. }}\n  "
                    for type in EXCLUDED_WIKIDATA_SUBCLASSES
                ]
            )
            + ''.join(
                [
                    f"FILTER NOT EXISTS {{ ?item wdt:P31 wd:{type}. }}\n  "
                    for type in EXCLUDED_WIKIDATA_INSTANCES
                ]
            )
            + ''.join(
                [
                    f"FILTER NOT EXISTS {{ ?item wdt:P136 wd:{type}. }}\n  "
                    for type in EXCLUDED_WIKIDATA_GENRES
                ]
            )
            + '''
  FILTER (!CONTAINS(STR(?page), "/"))
  SERVICE wikibase:label { bd:serviceParam wikibase:language "[AUTO_LANGUAGE],mul,'''
            + self.langcode
            + '''". }
}'''
        )

    def _sparql_url(self, category: str) -> str:
        params = {"format": "json", "query": self._sparql_query(category)}
        return update_url_with_params(WIKIDATA_API_URL, params)

    @property
    def wikisource_api_url(self) -> str:
        return f"https://{self.langcode}.wikisource.org/w/api.php"

    @property
    def all_wikidata_category_urls(self) -> list[str]:
        return [self._sparql_url(c) for c in self._included_categories]

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
        langcode="en",
        ol_langcode="eng",
        category_prefix="Category",
        included_categories=["Validated_texts"],
        excluded_categories=[
            "Subpages",
            "Posters",
            "Memoranda",
            "Legislation-CAGov",
            "Constitutional documents",
            "National constitutions",
            "Manuscripts",
            "Political tracts",
            "Proclamations",
            "Declarations of independence",
            "Pamphlets",
            "Forms of government",
            "PD-USGov",
            "PD-CAGov",
            "PD-UKGov",
            "Early modern speeches",
            "Sermons",
            "PD-EdictGov",
        ],
    )
]


class BookRecord:
    def set_publish_date(self, publish_date: str | None) -> None:
        self.publish_date = publish_date

    def add_publishers(self, publishers: list[str]) -> None:
        self.publishers.extend([a for a in publishers if a not in self.publishers])

    def set_edition(self, edition: str | None) -> None:
        self.edition = edition

    def set_isbn(self, isbn: str | None) -> None:
        self.isbn = isbn

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

    def set_imagename(self, imagename: str | None) -> None:
        self.imagename = imagename

    def add_categories(self, categories: list[str]) -> None:
        self.categories.extend([a for a in categories if a not in self.categories])

    def set_title(self, title: str | None) -> None:
        self.title = title

    @property
    def wikisource_id(self) -> str:
        return f"{self.language.langcode}:{self.label}"

    @property
    def source_records(self) -> list[str]:
        return [f"wikisource:{self.wikisource_id}"]

    @staticmethod
    def _format_author(name: HumanName) -> str:
        ln = name.last
        suf = f" {name.suffix}" if name.suffix != "" else ""
        ti = f"{name.title} " if name.title != "" else ""
        fn = name.first
        mid = f" {name.middle}" if name.middle != "" else ""
        return f"{ln}{suf}, {ti}{fn}{mid}"

    def __init__(
        self,
        language: LangConfig,
        label: str,
        title: str | None = None,
        publish_date: str | None = None,
        edition: str | None = None,
        authors: list[str] | None = None,
        description: str | None = None,
        subjects: list[str] | None = None,
        cover: str | None = None,
        isbn: str | None = None,
        publishers: list[str] | None = None,
        imagename: str | None = None,
        categories: list[str] | None = None,
    ):
        self.authors: list[HumanName] = []
        self.categories: list[str] = []
        self.subjects: list[str] = []
        self.publishers: list[str] = []
        self.label = label
        self.language = language
        self.set_publish_date(publish_date)
        self.set_edition(edition)
        if authors is not None:
            self.add_authors(authors)
        self.set_description(description)
        if subjects is not None:
            self.add_subjects(subjects)
        self.set_cover(cover)
        self.set_isbn(isbn)
        if publishers is not None:
            self.add_publishers(publishers)
        self.set_imagename(imagename)
        if categories is not None:
            self.add_categories(categories)
        self.set_title(title)

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
        # is this the right property name?
        # what other properties should we be getting?
        if self.isbn is not None:
            output["isbn"] = self.isbn
        if len(self.publishers) > 0:
            output["publishers"] = self.publishers
        return output


def update_record_with_wikisource_metadata(
    book: BookRecord, new_data: dict, image_titles: list[str]
):
    if "categories" in new_data:
        book.add_categories([cat["title"] for cat in new_data["categories"]])

    # Find png/jpg filename
    if book.imagename is None and "images" in new_data:
        # Ignore svgs, these are wikisource photos and other assets that aren't properties of the book.
        linked_images = [
            i
            for i in new_data["images"]
            if not i["title"].endswith(".svg") and i["title"] != ""
        ]
        # Set this as the book"s image name, which will be used later use its URL in the import
        if len(linked_images) > 0:
            imagename = linked_images[0]["title"]
            book.set_imagename(imagename)
            # Add it to image_titles in order to look up its URL later
            if imagename not in image_titles:
                image_titles.append(imagename)

    # Parse other params from the infobox
    infobox = next(
        (
            d["slots"]["main"]["*"]
            for d in new_data["revisions"]
            if "revisions" in new_data and "slots" in d and "main" in d["slots"] and "*" in d["slots"]["main"]
        ),
        None,
    )
    # Exit if infobox doesn't exist
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
            match = re.search(r"\d{4}", yr)
            if match:
                book.set_publish_date(match.group(0))
        except ValueError:
            pass

    if len(book.authors) == 0:
        try:
            author = template.get("author").value.strip()
            if author != "":
                authors = re.split(r"(?:\sand\s|,\s?)", author)
                if len(authors) > 0:
                    book.add_authors(authors)
        except ValueError:
            pass

    if book.description is None:
        try:
            # Replace HTML and markup newlines with \n, because they get stripped otherwise
            raw = template.get("notes").value.strip()
            raw_spaced = re.sub(r"(:?<br/>|\{\{rule\}\})", "\n", raw)
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


def print_records(records: list[BookRecord], cfg: LangConfig):
    folder_path = "scripts/providers/batch_output/"
    now = time.gmtime(time.time())
    os.makedirs(os.path.dirname(folder_path), exist_ok=True)
    file_path = f"{folder_path}/wikisource-{now.tm_year}.{now.tm_mon}.{now.tm_mday}-{now.tm_hour}.{now.tm_min}.{now.tm_sec}-{cfg.langcode}.jsonl"
    with open(file_path, "w", encoding="utf-8") as file:
        for rec in records:
            r = {"ia_id": rec.source_records[0], "data": rec.to_dict()}
            file.write(json.dumps(r) + "\n")


def scrape_wikisource_api(url: str, cfg: LangConfig, imports: dict[str, BookRecord]):
    cont_url = url
    image_titles: list[str] = []

    # Continue until you"ve reached the end of paginated results
    while True:
        try:
            r = requests.get(cont_url, stream=True)
            data = r.json()
        except requests.exceptions.RequestException as e:
            # If too many requests error, wait 10 seconds and try again
            if e.response is None or e.response.status_code in (429, 503):
                time.sleep(10)
            else:
                raise SystemExit(e)
            continue

        if "query" not in data or "pages" not in data["query"]:
            break
        results = data["query"]["pages"]

        for page in results.values():
            page_identifier = quote(page["title"].replace(' ', '_'))

            book = next(
                (book for book in imports.values() if book.label == page_identifier),
                None,
            )
            if book:
                # MediaWiki"s API paginates through pages, page categories, and page images separately.
                # This means that when you hit this API requesting both revision (infobox) and image data,
                # sequential paginated API responses might contain the same Wikisource book entries, but with different subsets of its properties.
                # i.e. Page 1 might give you 50 books where only the first 10 have image data,
                # and page 2 might give you the same 50 books but only the last 10 have image data.
                update_record_with_wikisource_metadata(book, page, image_titles)

        # Proceed to next page of API results
        if "continue" not in data:
            break
        cont_url = update_url_with_params(url, data["continue"])

    if len(image_titles) > 0:
        # The API calls from earlier that retrieved page data aren't able to return image URLs.
        # The "imageinfo" prop, which contains URLs, does nothing unless you"re querying image names directly.
        # Here we"ll query as many images as possible in one API request, build a map of the results,
        # and then set the cover URL for any book that is associated to the image filename.
        image_map: dict[str, str] = {}

        # API will only allow up to 50 images at a time to be requested, so do this in chunks.
        for index in range(0, len(image_titles), 50):
            end = min(index + 50, len(image_titles))

            image_api_url = update_url_with_params(
                cfg.wikisource_api_url,
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
                try:
                    r2 = requests.get(working_url, stream=True)
                    data = r2.json()
                except requests.exceptions.RequestException as e:
                    # If too many requests error, wait 10 seconds and try again
                    if e.response is None or e.response.status_code in (429, 503):
                        time.sleep(10)
                    else:
                        raise SystemExit(e)
                    continue

                if "query" not in data or "pages" not in data["query"]:
                    break
                results = data["query"]["pages"]

                for page_identifier in results:
                    image_hit = results[page_identifier]
                    if (
                        "imageinfo" in image_hit
                        and image_hit["title"] not in image_map
                        and len(image_hit["imageinfo"]) > 0
                        and "url" in image_hit["imageinfo"][0]
                    ):
                        image_map[image_hit["title"]] = image_hit["imageinfo"][0]["url"]

                # next page of image hits, if necessary
                if "continue" not in data:
                    break
                working_url = update_url_with_params(image_api_url, data["continue"])

        # Set cover URLs to books according to which ones use the given image filenames.
        for page_identifier, book in imports.items():
            if book.imagename is not None and book.imagename in image_map:
                book.set_cover(image_map[book.imagename])


def scrape_wikidata_api(url: str, cfg: LangConfig, imports: dict[str, BookRecord]):
    # Unsure if this is supposed to be paginated. Validated Texts only returns one page of JSON results.
    # The "while true" here is simply to retry requests that fail due to API limits.
    print("Fetching Wikidata IDs...")
    while True:
        try:
            r = requests.get(url, stream=True)
            data = r.json()
        except requests.exceptions.RequestException as e:
            # If too many requests error, wait 10 seconds and try again
            if e.response is None or e.response.status_code in (429, 503):
                time.sleep(10)
            else:
                raise SystemExit(e)
            continue

        if "results" not in data or "bindings" not in data["results"]:
            print("Invalid Wikidata response. Exiting.")
            break

        item_ids = []

        for obj in [
            d
            for d in data["results"]["bindings"]
            if "item" in d and "value" in d["item"]
        ]:

            item_id = get_wd_item_id(obj["item"]["value"])
            item_ids.append(item_id)
            imports[item_id] = BookRecord(
                label=quote(obj["page"]["value"].replace(' ', '_')),
                language=cfg,
            )

        print(f"wikidata query returned {len(item_ids)} potential book IDs")

        if len(item_ids) == 0:
            print("Exiting.")
            break

        # Get book metadata from the wikidata API using 50 wikidata book IDs at a time
        start = 0
        end = min(50, len(item_ids))

        while start < len(item_ids):
            print(f"processing query results {start} to {end}")

            query = (
                '''SELECT DISTINCT
  ?item
  ?itemLabel
  ?title
  ?authorLabel
  ?publisherLabel
  ?editionLabel
  ?date
  ?isbn
  ?subjectLabel
  ?imageUrl
WHERE {
  VALUES ?item {'''
                + ''.join([f"wd:{id}\n    " for id in item_ids[start:end]])
                + '''}
  OPTIONAL { ?item wdt:P1476 ?title. }
  OPTIONAL { ?item wdt:P50 ?author. }
  OPTIONAL { ?item wdt:P123 ?publisher. }
  OPTIONAL { ?item wdt:P393 ?edition. }
  OPTIONAL { ?item wdt:P577 ?date. }
  OPTIONAL { ?item wdt:P212 ?isbn. }
  OPTIONAL { ?item wdt:P921 ?subject. }
  OPTIONAL { ?item wdt:P18 ?image. }
  BIND(CONCAT("https://commons.wikimedia.org/wiki/Special:FilePath/", REPLACE(STR(?image), "^.*[/#]", "")) AS ?imageUrl)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "[AUTO_LANGUAGE],mul,'''
                + cfg.langcode
                + '''". }
}'''
            )
            # Get most metadata from wikidata
            metadata_url = update_url_with_params(
                WIKIDATA_API_URL, {"format": "json", "query": query}
            )

            try:
                r2 = requests.get(metadata_url, stream=True)
                data = r2.json()
            except requests.exceptions.RequestException as e:
                # If too many requests error, wait 10 seconds and try again
                if e.response is None or e.response.status_code in (429, 503):
                    time.sleep(10)
                    print("retrying...")
                else:
                    raise SystemExit(e)
                continue

            # Increase start and end for the next loop iteration
            start = end
            end = min(start + 50, len(item_ids))

            if "results" not in data or "bindings" not in data["results"]:
                continue

            ids_for_wikisource_api = []
            results = [
                obj
                for obj in data["results"]["bindings"]
                if "item" in obj
                and "value" in obj["item"]
                and not (
                    (
                        ("title" not in obj or "value" not in obj["title"])
                        and ("itemLabel" not in obj or "value" not in obj["itemLabel"])
                    )
                    # Don't include duplicate results that are just the same book but with its title in a different language
                    or (
                        "title" in obj
                        and "xml:lang" in obj["title"]
                        and obj["title"]["xml:lang"] != cfg.langcode
                    )
                )
            ]

            for obj in results:
                title: str = (
                    obj["title"]["value"]
                    if "title" in obj and "value" in obj["title"]
                    else obj["itemLabel"]["value"]
                )
                id = get_wd_item_id(obj["item"]["value"])
                impt = imports[id]
                impt.set_title(title)

                ids_for_wikisource_api.append(impt.label)

                # Author
                if "authorLabel" in obj and "value" in obj["authorLabel"]:
                    impt.add_authors([obj["authorLabel"]["value"]])

                # Publisher
                if "publisherLabel" in obj and "value" in obj["publisherLabel"]:
                    impt.add_publishers([obj["publisherLabel"]["value"]])

                # Edition
                if "editionLabel" in obj and "value" in obj["editionLabel"]:
                    impt.set_edition(obj["editionLabel"]["value"])

                # Subject
                if "subjectLabel" in obj and "value" in obj["subjectLabel"]:
                    impt.add_subjects([obj["subjectLabel"]["value"]])

                # Date
                if "date" in obj and "value" in obj["date"]:
                    impt.set_publish_date(
                        obj["date"]["value"]
                    )  # does this timestamp need to be formatted?

            # For some reason, querying 50 titles can sometimes bring back more than 50 results,
            # so we'll still explicitly do wikisource scraping in chunks of exactly 50.
            for wsstart in range(0, len(ids_for_wikisource_api), 50):
                wsend = wsstart + 50

                wsend = min(wsstart + 50, len(ids_for_wikisource_api))
                # Get more info from Wikisource infoboxes that Wikidata statements don't have, like subjects and descriptions
                ws_api_url = update_url_with_params(
                    cfg.wikisource_api_url,
                    {
                        "action": "query",
                        "titles": "|".join(ids_for_wikisource_api[wsstart:wsend]),
                        # Relevant page data. The inclusion of |revisions, and rvprop/rvslots, are used to get book info from the page"s infobox.
                        "prop": "categories|revisions|images",
                        "rvprop": "content",
                        "rvslots": "main",
                        # Include as many categories and images per response as possible
                        "cllimit": "max",
                        "imlimit": "max",
                        "format": "json",
                    },
                )
                scrape_wikisource_api(ws_api_url, cfg, imports)

            # Use wikidata image URL if it exists and wikisource didn't return one.
            for obj in results:
                id = get_wd_item_id(obj["item"]["value"])
                impt = imports[id]
                if (
                    impt.imagename is None
                    and "imageUrl" in obj
                    and "value" in obj["imageUrl"]
                ):
                    impt.set_imagename(obj["imageUrl"]["value"])
                    impt.set_cover(obj["imageUrl"]["value"])
        break


# If we want to process all Wikisource pages in more than one category, we have to do one API call per category per language.
def process_all_books(cfg: LangConfig):
    imports: dict[str, BookRecord] = {}
    for url in cfg.all_wikidata_category_urls:
        scrape_wikidata_api(url, cfg, imports)
    batch: list[BookRecord] = []
    for book in list(imports.values()):
        # Skip if the book belongs to an ignored Wikisource page category, such as subpages (chapters), posters, etc
        excluded_categories = [
            c for c in book.categories if c in cfg.excluded_categories
        ]
        if len(excluded_categories) > 0:
            continue
        batch.append(book)
    if len(batch) > 0:
        print_records(batch, cfg)


def main(ol_config: str):
    """
    :param str ol_config: Path to openlibrary.yml file
    """
    load_config(ol_config)

    for ws_language in ws_languages:
        process_all_books(ws_language)


if __name__ == "__main__":
    FnToCLI(main).run()
