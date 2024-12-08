"""
To Run:

PYTHONPATH=. python ./scripts/providers/import_wikisource.py /olsystem/etc/openlibrary.yml
"""

import itertools
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlparse, urlunparse

# Using both mwparserfromhell and wikitextparser because the former doesn't have a markup stripper
# and the latter doesn't have a method to get a template prop by key.
import mwparserfromhell as mw
import requests
import wikitextparser as wtp
from nameparser import HumanName

from openlibrary.config import load_config
from openlibrary.utils import uniq
from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI

logger = logging.getLogger("openlibrary.importer.wikisource")


def update_url_with_params(url: str, new_params: dict[str, str]):
    url_parts = list(urlparse(url))
    query = dict(parse_qsl(url_parts[4]))
    query.update(new_params)
    url_parts[4] = urlencode(query, quote_via=quote)
    return urlunparse(url_parts)


def extract_year(date_string: str) -> str | None:
    match = re.match(r'(\d{4})', date_string)
    return match.group(1) if match else None


# Exclude Wikidata results which are direct instances of these things.
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
    "Q15916459",  # plea
]

# Exclude Wikidata results which belong to subclasses of these things.
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

# Exclude Wikidata results which belong to these genres.
EXCLUDED_WIKIDATA_GENRES = [
    "Q603773",  # lectures
    "Q861911",  # orations
    "Q35760",  # essays
    "Q60797",  # sermons
    "Q133492",  # letters
]

WIKIDATA_API_URL = "https://query.wikidata.org/bigdata/namespace/wdq/sparql"


def get_wd_item_id(string: str):
    return string.split('/')[-1]


@dataclass
class LangConfig:
    langcode: str
    ol_langcode: str
    category_prefix: str
    included_category_names: list[str]
    excluded_category_names: list[str]

    def _catformat(self, category: str) -> str:
        return f"{self.category_prefix}:{category}"

    def _sparql_query(self, category: str) -> str:
        # This gets the wikisource page names and wikidata item IDs from a Wikisource generator.
        # The generator is a pretty heavy lift, so fetching more metadata will be done in a separate query and in batches.
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
        return [self._sparql_url(c) for c in self.included_category_names]

    @property
    def excluded_categories(self) -> list[str]:
        return [self._catformat(c) for c in self.excluded_category_names]


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
        included_category_names=["Validated_texts"],
        excluded_category_names=[
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
            "Film",
        ],
    )
]


def format_contributor(raw_name: str) -> str:
    name = HumanName(raw_name)
    fn = f"{name.first} " if name.first != "" else ""
    mid = f"{name.middle} " if name.middle != "" else ""
    ln = name.last
    suf = f" {name.suffix}" if name.suffix != "" else ""
    return f"{fn}{mid}{ln}{suf}"


@dataclass
class Author:
    friendly_name: str | None = None
    birth_date: str | None = None
    death_date: str | None = None

    def __hash__(self):
        return hash((self.friendly_name, self.birth_date, self.death_date))


@dataclass
class BookRecord:
    langconfig: LangConfig
    wikisource_page_title: str
    title: str | None = None
    publish_date: str | None = None
    edition: str | None = None
    authors: list[Author] = field(default_factory=list)
    illustrators: list[str] = field(default_factory=list)
    description: str | None = None
    subjects: list[str] = field(default_factory=list)
    cover: str | None = None
    publishers: list[str] = field(default_factory=list)
    imagename: str | None = None
    categories: list[str] = field(default_factory=list)
    ia_id: str | None = None
    publish_places: list[str] = field(default_factory=list)
    page_count: int | None = None
    oclcs: list[str] = field(default_factory=list)
    lccn: str | None = None
    isbn10: str | None = None
    isbn13: str | None = None

    def add_publishers(self, publishers: list[str]) -> None:
        self.publishers = uniq(self.publishers + publishers)

    def add_publish_place(self, places: list[str]) -> None:
        self.publish_places = uniq(self.publish_places + places)

    def add_authors(self, authors: list[Author]) -> None:
        self.authors = uniq(
            self.authors + authors, key=lambda author: author.friendly_name
        )

    def add_illustrators(self, illustrators: list[str]) -> None:
        self.illustrators = uniq(self.illustrators + illustrators)

    def add_subjects(self, subjects: list[str]) -> None:
        self.subjects = uniq(self.subjects + subjects)

    def add_categories(self, categories: list[str]) -> None:
        self.categories = uniq(self.categories + categories)

    def add_oclcs(self, oclcs: list[str]) -> None:
        self.oclcs = uniq(self.oclcs + oclcs)

    @property
    def wikisource_id(self) -> str:
        return f"{self.langconfig.langcode}:{self.wikisource_page_title}"

    @property
    def source_records(self) -> list[str]:
        records = [f"wikisource:{self.wikisource_id}"]
        if self.ia_id is not None:
            records.insert(0, f"ia:{self.ia_id}")
        return records

    def to_dict(self):
        publishers = ["Wikisource"]
        publishers.extend(self.publishers)
        output = {
            "title": self.title,
            "source_records": self.source_records,
            "identifiers": {"wikisource": [self.wikisource_id]},
            "languages": [self.langconfig.ol_langcode],
            "ia_id": self.source_records[0],
        }
        if self.publish_date is not None:
            output["publish_date"] = self.publish_date
        if self.edition is not None:
            output["edition_name"] = self.edition
        if self.authors:
            output["authors"] = [
                {
                    "name": author.friendly_name,
                    "birth_date": author.birth_date,
                    "death_date": author.death_date,
                }
                for author in self.authors
            ]
        if self.description is not None:
            output["description"] = self.description
        if self.subjects:
            output["subjects"] = self.subjects
        if self.cover is not None:
            output["cover"] = self.cover
        if publishers:
            output["publishers"] = publishers
        if self.publish_places:
            output["publish_places"] = self.publish_places
        if self.page_count:
            output["pagination"] = self.page_count
        if self.oclcs:
            output["oclc_numbers"] = self.oclcs
        if self.lccn:
            output["lccn"] = self.lccn
        if self.illustrators:
            output["contributions"] = self.illustrators
        if self.isbn10:
            output["isbn_10"] = self.isbn10
        if self.isbn13:
            output["isbn_13"] = self.isbn13

        return output


def fetch_until_successful(url: str) -> dict:
    for _ in range(5):
        try:
            response = requests.get(url, stream=True)
            return response.json()
        except requests.exceptions.RequestException as error:
            # If too many requests error, or API overloaded, wait 10 seconds and try again
            # In testing this feature, this could return a 429 error, 503 error, or an empty response body
            if error.response is None or error.response.status_code in (429, 503):
                time.sleep(10)
            else:
                raise SystemExit(error)
    raise SystemExit(
        f"could not fetch {url} after 5 tries. You may be rate limited, try again later"
    )


def update_record_with_wikisource_metadata(
    book: BookRecord, book_id: str, new_data: dict, author_map: dict[str, list[str]]
):
    if "categories" in new_data:
        book.add_categories([cat["title"] for cat in new_data["categories"]])

    # Parse other params from the infobox
    revision_data = new_data.get("revisions", [])
    infobox = next(
        (
            d["slots"]["main"]["*"]
            for d in revision_data
            if "slots" in d and "main" in d["slots"] and "*" in d["slots"]["main"]
        ),
        None,
    )
    # Exit if infobox doesn't exist
    if infobox is None:
        return
    wikicode = mw.parse(infobox)
    templates = wikicode.filter_templates()
    if not templates:
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
            book.publish_date = extract_year(yr)
        except ValueError:
            pass

    if not [b for b in author_map if book_id in author_map[b]] and not book.authors:
        try:
            author = template.get("author").value.strip()
            if author != "":
                authors = re.split(r"(?:\sand\s|,\s?)", author)
                if authors:
                    book.add_authors(
                        [Author(friendly_name=format_contributor(a)) for a in authors]
                    )
        except ValueError:
            pass

    if not book.illustrators:
        try:
            illustrator = template.get("illustrator").value.strip()
            if illustrator != "":
                illustrators = re.split(r"(?:\sand\s|,\s?)", illustrator)
                if illustrators:
                    book.add_illustrators([format_contributor(a) for a in illustrators])
        except ValueError:
            pass

    if book.description is None:
        try:
            # Replace HTML and markup newlines with \n, because they get stripped otherwise
            raw = template.get("notes").value.strip()
            raw_spaced = re.sub(r"(:?<br/>|\{\{rule\}\})", "\n", raw)
            notes = wtp.remove_markup(raw_spaced)
            if notes != "":
                book.description = notes
        except ValueError:
            pass

    try:
        subject: str = template.get("portal").value.strip()
        if subject != "":
            book.add_subjects(subject.split("/"))
    except ValueError:
        pass


def print_records(records: list[BookRecord]):
    for rec in records:
        r = rec.to_dict()
        print(json.dumps(r))


def scrape_wikisource_api(
    url: str,
    imports: dict[str, BookRecord],
    author_map: dict[str, list[str]],
):
    cont_url = url

    # Continue until you've reached the end of paginated results
    while True:
        data = fetch_until_successful(cont_url)

        if "query" not in data or "pages" not in data["query"]:
            break

        results = data["query"]["pages"]

        for page in results.values():
            page_identifier = quote(page["title"].replace(' ', '_'))

            key = next(
                (
                    key
                    for key in imports
                    if imports[key].wikisource_page_title == page_identifier
                ),
                None,
            )
            if not key:
                print(f"{page_identifier} not found in result set")
                continue
            book = imports[key]
            # MediaWiki's API paginates through pages, page categories, and page images separately.
            # This means that when you hit this API requesting both revision (infobox) and image data,
            # sequential paginated API responses might contain the same Wikisource book entries, but with different subsets of its properties.
            # i.e. Page 1 might give you 50 books where only the first 10 have image data,
            # and page 2 might give you the same 50 books but only the last 10 have image data.
            update_record_with_wikisource_metadata(book, key, page, author_map)

        # Proceed to next page of API results
        if "continue" not in data:
            break
        cont_url = update_url_with_params(url, data["continue"])


def update_import_with_wikidata_api_response(
    impt: BookRecord, book_id: str, obj: Any, author_map: dict[str, list[str]]
):

    # Author ID: Fetch more data about authors at a later time. WD query times out if we include author data
    if "author" in obj and "value" in obj["author"]:
        author_id = get_wd_item_id(obj["author"]["value"])
        if author_id not in author_map:
            author_map[author_id] = []
        author_map[author_id].append(book_id)
    # If author isn't a WD object, add them as plaintext
    elif "authorLabel" in obj and "value" in obj["authorLabel"]:
        impt.add_authors(
            [Author(friendly_name=format_contributor(obj["authorLabel"]["value"]))]
        )

    # Illustrators
    if "illustratorLabel" in obj and "value" in obj["illustratorLabel"]:
        impt.add_illustrators([format_contributor(obj["illustratorLabel"]["value"])])

    # Publisher
    if ("publisher" in obj and "value" in obj["publisher"]) or (
        "publisherName" in obj and "value" in obj["publisherName"]
    ):
        impt.add_publishers(
            [
                (
                    obj["publisherName"]["value"]
                    if "publisherLabel" not in obj
                    else obj["publisherLabel"]["value"]
                )
            ]
        )

    # Edition
    if "editionLabel" in obj and "value" in obj["editionLabel"]:
        impt.edition = obj["editionLabel"]["value"]

    # Subject
    if "subjectLabel" in obj and "value" in obj["subjectLabel"]:
        impt.add_subjects([obj["subjectLabel"]["value"]])

    # Date
    if "date" in obj and "value" in obj["date"]:
        impt.publish_date = extract_year(obj["date"]["value"])

    # IA ID
    if "iaId" in obj and "value" in obj["iaId"]:
        impt.ia_id = obj["iaId"]["value"]

    # Publish place
    if "publicationPlaceLabel" in obj and "value" in obj["publicationPlaceLabel"]:
        impt.add_publish_place([obj["publicationPlaceLabel"]["value"]])

    # OCLC
    if "oclcLabel" in obj and "value" in obj["oclcLabel"]:
        impt.add_oclcs([obj["oclcLabel"]["value"]])

    # LCCN
    if "lccn" in obj and "value" in obj["lccn"]:
        impt.lccn = obj["lccn"]["value"]

    # ISBN10
    if "isbn10" in obj and "value" in obj["isbn10"]:
        impt.isbn10 = obj["isbn10"]["value"]

    # ISBN13
    if "isbn13" in obj and "value" in obj["isbn13"]:
        impt.isbn13 = obj["isbn13"]["value"]


def scrape_wikidata_api(
    url: str,
    cfg: LangConfig,
    imports: dict[str, BookRecord],
    author_map: dict[str, list[str]],
):
    # Unsure if this is supposed to be paginated. Validated Texts only returns one page of JSON results.
    # The "while true" here is simply to retry requests that fail due to API limits.
    data = fetch_until_successful(url)

    if "results" not in data or "bindings" not in data["results"]:
        print("Invalid Wikidata response. Exiting.")
        return

    item_ids = []

    for binding in data["results"]["bindings"]:
        if "value" not in binding.get('item', {}):
            print("no value in binding:", binding)
            continue

        item_id = get_wd_item_id(binding["item"]["value"])
        item_ids.append(item_id)
        imports[item_id] = BookRecord(
            wikisource_page_title=quote(binding["page"]["value"].replace(' ', '_')),
            langconfig=cfg,
        )

    if not item_ids:
        print("Exiting.")
        return

    # Get book metadata from the wikidata API using 50 wikidata book IDs at a time
    for batch in itertools.batched(item_ids, 50):

        # "Title" and "page" (retrieved from the previous query) are often similar, but sometimes not exactly the same.
        # "Page" (the wikisource page ID) will sometimes contain extra info like the year of publishing, etc,
        # and is used to hyperlink back to Wikisource.
        # "Title" on the other hand is the actual title of the work that we would call it on OL.
        # Publisher data is weird. This book https://www.wikidata.org/wiki/Q51423720 for example
        # returns a weird URL for publisherLabel if retrieved with wdt:P123 instead of p:P123
        # but it has a qualifier property, pq:P1932, which contains the raw text (non wikidata item) publisher name if it exists.
        query = (
            '''SELECT DISTINCT
  ?item
  ?itemLabel
  ?title
  ?author
  ?authorLabel
  ?illustrator
  ?illustratorLabel
  ?publisher
  ?publisherName
  ?publicationPlaceLabel
  ?editionLabel
  ?pageCount
  ?date
  ?subjectLabel
  ?imageUrl
  ?iaId
  ?oclcLabel
  ?lccn
  ?isbn10
  ?isbn13
WHERE {
  VALUES ?item {'''
            + ''.join([f"wd:{id}\n    " for id in batch])
            + '''}
  OPTIONAL { ?item wdt:P1476 ?title. }
  OPTIONAL { ?item wdt:P50 ?author. }
  OPTIONAL { ?item wdt:P110 ?illustrator. }
  OPTIONAL {
    ?item p:P123 ?publisherStatement.
    ?publisherStatement ps:P123 ?publisher.
    ?publisherStatement pq:P1932 ?publisherName.
  }
  OPTIONAL { ?item wdt:P291 ?publicationPlace. }
  OPTIONAL { ?item wdt:P393 ?edition. }
  OPTIONAL { ?item wdt:P577 ?date. }
  OPTIONAL { ?item wdt:P921 ?subject. }
  OPTIONAL { ?item wdt:P18 ?image. }
  OPTIONAL { ?item wdt:P724 ?iaId. }
  OPTIONAL { ?item wdt:P1104 ?pageCount. }
  OPTIONAL { ?item wdt:P243 ?oclc. }
  OPTIONAL { ?item wdt:P244 ?lccn. }
  OPTIONAL { ?item wdt:P957 ?isbn10. }
  OPTIONAL { ?item wdt:P212 ?isbn13. }
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

        data = fetch_until_successful(metadata_url)

        if "results" not in data or "bindings" not in data["results"]:
            continue

        ids_for_wikisource_api = []

        results = [
            obj
            for obj in data["results"]["bindings"]
            if "item" in obj
            and "value" in obj["item"]
            and not (
                # skip if no title or item label exists in the result
                (
                    ("title" not in obj or "value" not in obj["title"])
                    and ("itemLabel" not in obj or "value" not in obj["itemLabel"])
                )
                # skip if duplicate result of an existing record with a different language title
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
            book_id = get_wd_item_id(obj["item"]["value"])
            impt = imports[book_id]

            impt.title = title
            ids_for_wikisource_api.append(impt.wikisource_page_title)

            update_import_with_wikidata_api_response(impt, book_id, obj, author_map)

        # For some reason, querying 50 titles can sometimes bring back more than 50 results,
        # so we'll still explicitly do wikisource scraping in chunks of exactly 50.
        for ws_batch in itertools.batched(ids_for_wikisource_api, 50):

            # Get more info from Wikisource infoboxes that Wikidata statements don't have, like subjects and descriptions
            ws_api_url = update_url_with_params(
                cfg.wikisource_api_url,
                {
                    "action": "query",
                    # these are already urlencoded, decode them before they get urlencoded again
                    "titles": "|".join([unquote(id) for id in ws_batch]),
                    # Relevant page data. The inclusion of |revisions, and rvprop/rvslots, are used to get book info from the page's infobox.
                    "prop": "categories|revisions",
                    "rvprop": "content",
                    "rvslots": "main",
                    # Include as many categories per response as possible
                    "cllimit": "max",
                    "format": "json",
                },
            )

            scrape_wikisource_api(ws_api_url, imports, author_map)

        # Use wikidata image URL if it exists
        for obj in results:
            book_id = get_wd_item_id(obj["item"]["value"])
            impt = imports[book_id]

            if (
                impt.imagename is None
                and "imageUrl" in obj
                and "value" in obj["imageUrl"]
            ):
                impt.imagename = obj["imageUrl"]["value"]
                impt.cover = obj["imageUrl"]["value"]


def fix_contributor_data(
    imports: dict[str, BookRecord], map: dict[str, list[str]], cfg: LangConfig
):
    contributor_ids = list(map.keys())
    for batch in itertools.batched(contributor_ids, 50):
        query = (
            '''SELECT DISTINCT
  ?contributor
  ?contributorLabel
  ?birthDate
  ?deathDate
WHERE {
  VALUES ?contributor {'''
            + ''.join([f"wd:{id}\n    " for id in batch])
            + '''}
  OPTIONAL { ?contributor wdt:P569 ?birthDate. }
  OPTIONAL { ?contributor wdt:P570 ?deathDate. }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "[AUTO_LANGUAGE],mul,'''
            + cfg.langcode
            + '''". }
}'''
        )
        metadata_url = update_url_with_params(
            WIKIDATA_API_URL, {"format": "json", "query": query}
        )

        data = fetch_until_successful(metadata_url)

        if "results" not in data or "bindings" not in data["results"]:
            continue

        results = [
            obj
            for obj in data["results"]["bindings"]
            if "contributor" in obj and "value" in obj["contributor"]
        ]

        for obj in results:
            contributor_id = get_wd_item_id(obj["contributor"]["value"])

            # Don't include author if their name is incomplete, for whatever reason
            if "contributorLabel" in obj and "value" in obj["contributorLabel"]:
                contributor = Author(
                    friendly_name=format_contributor(obj["contributorLabel"]["value"])
                )

                if "birthDate" in obj and "value" in obj["birthDate"]:
                    contributor.birth_date = obj["birthDate"]["value"]

                if "deathDate" in obj and "value" in obj["deathDate"]:
                    contributor.death_date = obj["deathDate"]["value"]

                if contributor_id in map:
                    book_ids = map[contributor_id]
                    for book_id in book_ids:
                        imports[book_id].add_authors([contributor])


# If we want to process all Wikisource pages in more than one category, we have to do one API call per category per language.
def process_all_books(cfg: LangConfig):
    imports: dict[str, BookRecord] = {}
    author_map: dict[str, list[str]] = {}

    for url in cfg.all_wikidata_category_urls:
        scrape_wikidata_api(url, cfg, imports, author_map)

    fix_contributor_data(imports, author_map, cfg)

    batch: list[BookRecord] = []

    for book in list(imports.values()):
        # Skip if the book belongs to an ignored Wikisource page category, such as subpages (chapters), posters, etc
        excluded_categories = [
            c for c in book.categories if c in cfg.excluded_categories
        ]
        if excluded_categories:
            continue

        batch.append(book)

    if batch:
        print_records(batch)


def main(ol_config: str):
    """
    :param str ol_config: Path to openlibrary.yml file
    """
    load_config(ol_config)

    for ws_language in ws_languages:
        process_all_books(ws_language)


if __name__ == "__main__":
    FnToCLI(main).run()
