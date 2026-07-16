import logging
import re
from functools import cached_property
from typing import TYPE_CHECKING, cast

import requests

import openlibrary.book_providers as bp
from openlibrary.edition_scorecard import EditionScorecard, EditionScorecardEvaluator
from openlibrary.solr.solr_types import SolrDocument
from openlibrary.solr.updater.abstract import AbstractSolrBuilder, AbstractSolrUpdater
from openlibrary.solr.utils import SolrUpdateRequest, get_solr_base_url
from openlibrary.utils import uniq
from openlibrary.utils.isbn import opposite_isbn

if TYPE_CHECKING:
    from openlibrary.solr.data_provider import DataProvider
    from openlibrary.solr.updater.work import WorkSolrBuilder

logger = logging.getLogger("openlibrary.solr")
re_edition_key_basename = re.compile("^[a-zA-Z0-9:.-]+$")
re_lang_key = re.compile(r"^/(?:l|languages)/([a-z]{3})$")
re_year = re.compile(r"\b(\d{4})\b")
re_solr_field = re.compile(r"^[-\w]+$", re.UNICODE)
re_not_az = re.compile("[^a-zA-Z]")


class EditionSolrUpdater(AbstractSolrUpdater):
    key_prefix = "/books/"
    thing_type = "/type/edition"

    async def update_key(self, thing: dict) -> tuple[SolrUpdateRequest, list[str]]:
        update = SolrUpdateRequest()
        new_keys: list[str] = []
        if thing["type"]["key"] == self.thing_type:
            if thing.get("works"):
                new_keys.append(thing["works"][0]["key"])
                # Make sure we remove any fake works created from orphaned editions
                update.deletes.append(thing["key"].replace("/books/", "/works/"))
            else:
                # index the edition as it does not belong to any work
                new_keys.append(thing["key"].replace("/books/", "/works/"))
        else:
            logger.info(
                "%r is a document of type %r. Checking if any work has it as edition in solr...",
                thing["key"],
                thing["type"]["key"],
            )
            work_key = solr_select_work(thing["key"])
            if work_key:
                logger.info("found %r, updating it...", work_key)
                new_keys.append(work_key)
        return update, new_keys


def solr_select_work(edition_key):
    """
    Get corresponding work key for given edition key in Solr.

    :param str edition_key: (ex: /books/OL1M)
    :return: work_key
    :rtype: str or None
    """
    # solr only uses the last part as edition_key
    edition_key = edition_key.split("/")[-1]

    if not re_edition_key_basename.match(edition_key):
        return None

    edition_key = solr_escape(edition_key)
    reply = requests.get(
        f"{get_solr_base_url()}/select",
        params={
            "wt": "json",
            "q": f"edition_key:{edition_key}",
            "rows": 1,
            "fl": "key",
        },
    ).json()
    if docs := reply["response"].get("docs", []):
        return docs[0]["key"]  # /works/ prefix is in solr


def solr_escape(query):
    """
    Escape special characters in Solr query.

    :param str query:
    :rtype: str
    """
    return re.sub(r'([\s\-+!()|&{}\[\]^"~*?:\\])', r"\\\1", query)


def is_sine_nomine(pub: str) -> bool:
    """Check if the publisher is 'sn' (excluding non-letter characters)."""
    return re_not_az.sub("", pub).lower() == "sn"


ARTICLE_PATTERN = re.compile(
    "^(an? |the |l[aeo]s? |l'|de la |el |il |un[ae]? |du |de[imrst]? |das |ein |eine[mnrs]? |bir )(.*)",
    flags=re.IGNORECASE,
)


def sort_title(title: str, subtitle: str | None) -> str:
    """Move leading articles to the end of the title for sorting purposes."""
    if subtitle:
        title = title + ": " + subtitle
    if match := ARTICLE_PATTERN.match(title):
        return f"{match.group(2)}, {match.group(1).strip()}"
    return title


class EditionSolrBuilder(AbstractSolrBuilder):
    def __init__(
        self,
        edition: dict,
        solr_work: WorkSolrBuilder | SolrDocument,
        db_work: dict | None,
        db_authors: list[dict],
        ia_metadata: bp.IALiteMetadata | None = None,
        data_provider: DataProvider | None = None,
    ):
        self._edition = edition
        self._solr_work = solr_work
        self._db_work = db_work
        self._authors = db_authors
        self._ia_metadata = ia_metadata
        self._data_provider = data_provider
        self._providers = list(bp.get_book_providers(edition))
        self._best_provider = self._providers[0] if self._providers else None

    @property
    def key(self):
        return self._edition["key"]

    @property
    def work_key(self) -> list[str]:
        # This is formatted like 'OL123W' ; bit awkward, but consistent with `edition_key`
        return [work_ref["key"].split("/")[-1] for work_ref in self._edition.get("works", [])]

    @property
    def title(self) -> str | None:
        return self._edition.get("title")

    @property
    def subtitle(self) -> str | None:
        return self._edition.get("subtitle")

    @property
    def title_sort(self) -> str | None:
        """
        Generates a formatted title string based on the ``title`` and
        ``subtitle`` attributes with any leading article removed and
        moved to the end of the string.

        :return: A formatted title string or None if ``title`` is not set.
        :rtype: str | None
        """
        if self.title:
            return sort_title(self.title, self.subtitle)
        return None

    @property
    def alternative_title(self) -> set[str]:
        """Get titles from the editions as alternative titles."""
        result: set[str] = set()
        full_title = self._edition.get("title")
        if not full_title:
            return result
        if self._edition.get("subtitle"):
            full_title += ": " + cast(str, self._edition["subtitle"])
        result.add(full_title)
        result.update(self._edition.get("work_titles", []))
        result.update(self._edition.get("other_titles", []))

        return result

    @property
    def chapter(self) -> list[str]:
        result = []
        olid = self._edition.get("key", "").split("/", 2)[-1]
        for chapter in self._edition.get("table_of_contents", []):
            # Check if plain string first
            if isinstance(chapter, str):
                result.append(f"{olid} | {chapter}")
                continue

            title = chapter.get("title", "")
            if chapter.get("subtitle"):
                title += f": {chapter['subtitle']}"
            if chapter.get("authors"):
                title += f" ({', '.join(a['name'] for a in chapter['authors'])})"

            result.append(f"{olid} | {chapter.get('label', '')} | {title} | {chapter.get('pagenum', '')}")
        return result

    @cached_property
    def cover_i(self) -> int | None:
        return next(
            (cover_id for cover_id in self._edition.get("covers", []) if cover_id != -1),
            None,
        )

    @cached_property
    def _cover_dimensions(self) -> tuple[int, int] | None:
        if not self.cover_i or not self._data_provider:
            return None
        return self._data_provider.get_cover_dimensions(self.cover_i)

    @property
    def cover_width(self) -> int | None:
        return self._cover_dimensions[0] if self._cover_dimensions else None

    @property
    def cover_height(self) -> int | None:
        return self._cover_dimensions[1] if self._cover_dimensions else None

    @property
    def lexile(self) -> int | None:
        lexile_str = self._edition.get("lexile")
        try:
            return int(lexile_str) if lexile_str else None
        except TypeError, ValueError:
            return None

    @property
    def language(self) -> list[str]:
        """Gets the 3 letter language codes (eg ['ger', 'fre'])"""
        result: list[str] = []
        for lang in self._edition.get("languages", []):
            m = re_lang_key.match(lang["key"] if isinstance(lang, dict) else lang)
            if m:
                result.append(m.group(1))
        return uniq(result)

    @property
    def publisher(self) -> list[str]:
        return uniq(publisher if not is_sine_nomine(publisher) else "Sine nomine" for publisher in self._edition.get("publishers", []))

    @property
    def number_of_pages(self) -> int | None:
        number_of_pages_str = self._edition.get("number_of_pages")
        try:
            return int(number_of_pages_str) if number_of_pages_str else None
        except TypeError, ValueError:
            return None

    @property
    def translation_of(self) -> str | None:
        return self._edition.get("translation_of")

    @property
    def format(self) -> str | None:
        return self._edition.get("physical_format")

    @property
    def edition_name(self) -> str | None:
        return self._edition.get("edition_name")

    @property
    def isbn(self) -> list[str]:
        """
        Get all ISBNs of the given edition. Calculates complementary ISBN13 for each
        ISBN10 and vice-versa. Does not remove '-'s.
        """
        isbns = []

        isbns += [isbn.replace("_", "").strip() for isbn in self._edition.get("isbn_13", [])]
        isbns += [isbn.replace("_", "").strip() for isbn in self._edition.get("isbn_10", [])]

        # Get the isbn13 when isbn10 is present and vice-versa.
        isbns += [opposite_isbn(v) for v in isbns]

        return uniq(isbn for isbn in isbns if isbn)

    @property
    def lccn(self) -> list[str]:
        return uniq(lccn.strip() for lccn in self._edition.get("lccn", []))

    @property
    def oclc(self) -> list[str]:
        return uniq(oclc.strip() for oclc in self._edition.get("oclc_numbers", []))

    @property
    def publish_date(self) -> str | None:
        return self._edition.get("publish_date")

    @property
    def publish_year(self) -> int | None:
        if self.publish_date:
            m = re_year.search(self.publish_date)
            return int(m.group(1)) if m else None
        else:
            return None

    @property
    def ia(self) -> str | None:
        ocaid = self._edition.get("ocaid")
        return ocaid.strip() if ocaid else None

    @property
    def ia_collection(self) -> list[str]:
        collections = self._ia_metadata["collection"] if self._ia_metadata else set()
        # Exclude fav-* collections because they're not useful to us.
        return [c for c in collections if not c.startswith("fav-")]

    @property
    def ia_box_id(self) -> list[str]:
        boxids = []
        if "ia_box_id" in self._edition:
            if isinstance(self._edition["ia_box_id"], str):
                boxids = [self._edition["ia_box_id"]]
            elif isinstance(self._edition["ia_box_id"], list):
                boxids = self._edition["ia_box_id"]
            else:
                logger.warning(f'Bad ia_box_id on {self.key}: "{self._edition["ia_box_id"]}"')
        if self._ia_metadata:
            boxids += list(self._ia_metadata.get("boxid") or [])

        return uniq(boxids, key=lambda x: x.lower())

    @property
    def _identifiers(self) -> dict:
        identifiers = {}
        for key, id_list in self._edition.get("identifiers", {}).items():
            solr_key = key.replace(".", "_").replace(",", "_").replace("(", "").replace(")", "").replace(":", "_").replace("/", "").replace("#", "").lower()
            m = re_solr_field.match(solr_key)
            if not m:
                logger.warning(f'Bad identifier on {self.key}: "{key}"')
                continue

            # Sometimes v can be None? So filter that out
            if values := uniq(v.strip() for v in id_list if v):
                identifiers[f"id_{solr_key}"] = values
        return identifiers

    @cached_property
    def ebook_access(self) -> bp.EbookAccess:
        if not self._best_provider:
            return bp.EbookAccess.NO_EBOOK
        elif isinstance(self._best_provider, bp.InternetArchiveProvider):
            return self._best_provider.get_access(self._edition, self._ia_metadata)
        else:
            return self._best_provider.get_access(self._edition)

    @property
    def ebook_provider(self) -> list[str]:
        return [provider.provider_name for provider in (self._providers or [])]

    @property
    def has_fulltext(self) -> bool:
        return self.ebook_access > bp.EbookAccess.UNCLASSIFIED

    @property
    def public_scan_b(self) -> bool:
        return self.ebook_access == bp.EbookAccess.PUBLIC

    def _get_description_text(self) -> str:
        """Extract description text, handling both plain strings and text_block dicts."""
        desc = self._edition.get("description")
        if isinstance(desc, dict):
            return desc.get("value", "")
        return desc or ""

    def get_scorecard(self) -> EditionScorecard:
        if isinstance(self._solr_work, dict):
            solr_work = self._solr_work
        else:
            # Don't include editions or we'll get an infinite loop!
            solr_work = self._solr_work.build(exclude=["editions"])

        return EditionScorecardForSolr(
            solr_edition=self,
            solr_work=solr_work,
            db_work=self._db_work,
            authors=self._authors or [],
        ).evaluate()

    @cached_property
    def _usefulness_scorecard(self) -> EditionScorecard:
        return self.get_scorecard()

    @property
    def usefulness_score(self) -> int:
        return self._usefulness_scorecard.score

    @property
    def usefulness_score_normalized(self) -> int:
        return self._usefulness_scorecard.score_normalized

    @property
    def access_score(self) -> int:
        return self._usefulness_scorecard.access.score

    @property
    def access_score_normalized(self) -> int:
        return self._usefulness_scorecard.access.score_normalized

    @property
    def discovery_score(self) -> int:
        return self._usefulness_scorecard.discovery.score

    @property
    def discovery_score_normalized(self) -> int:
        return self._usefulness_scorecard.discovery.score_normalized

    @property
    def evaluation_score(self) -> int:
        return self._usefulness_scorecard.evaluation.score

    @property
    def evaluation_score_normalized(self) -> int:
        return self._usefulness_scorecard.evaluation.score_normalized

    def build(self, exclude: list[str] | None = None) -> SolrDocument:
        """
        Build the solr document for the given edition to store as a nested
        document

        Completely override parent class method to handle some peculiar
        fields
        """
        from openlibrary.solr.updater.work import WorkSolrBuilder  # noqa: PLC0415

        exclude = exclude or []

        # Avoid calling self._solr_work.build(), since that makes db requests for eg ratings
        if self._solr_work and isinstance(self._solr_work, WorkSolrBuilder):
            author_fields = {
                "author_name": self._solr_work.author_name,
                "author_key": self._solr_work.author_key,
                "author_alternative_name": list(self._solr_work.author_alternative_name),
                "author_facet": self._solr_work.author_facet,
            }
        elif self._solr_work and isinstance(self._solr_work, dict):
            author_fields = {
                "author_name": self._solr_work.get("author_name") or [],
                "author_key": self._solr_work.get("author_key") or [],
                "author_alternative_name": self._solr_work.get("author_alternative_name") or [],
                "author_facet": self._solr_work.get("author_facet") or [],
            }
        else:
            author_fields = {}

        solr_doc = {
            "key": self.key,
            "work_key": self.work_key,
            "type": "edition",
            # Display data
            "title": self.title,
            "subtitle": self.subtitle,
            "alternative_title": list(self.alternative_title),
            "chapter": self.chapter,
            "cover_i": self.cover_i,
            "cover_width": self.cover_width,
            "cover_height": self.cover_height,
            "language": self.language,
            # Duplicate the author data from the work
            **author_fields,
            "edition_name": ([self.edition_name] if self.edition_name else None),
            # Misc useful data
            "publisher": self.publisher,
            "format": [self.format] if self.format else None,
            "publish_date": [self.publish_date] if self.publish_date else None,
            "publish_year": [self.publish_year] if self.publish_year else None,
            # Usefulness scores
            "usefulness_score": self.usefulness_score,
            "usefulness_score_normalized": self.usefulness_score_normalized,
            "access_score": self.access_score,
            "access_score_normalized": self.access_score_normalized,
            "discovery_score": self.discovery_score,
            "discovery_score_normalized": self.discovery_score_normalized,
            "evaluation_score": self.evaluation_score,
            "evaluation_score_normalized": self.evaluation_score_normalized,
            # Identifiers
            "isbn": self.isbn,
            "lccn": self.lccn,
            "oclc": self.oclc,
            **self._identifiers,
            # IA
            "ia": [self.ia] if self.ia else None,
            "ia_collection": self.ia_collection,
            "ia_box_id": self.ia_box_id,
            # Ebook access
            "ebook_access": self.ebook_access.to_solr_str(),
            "ebook_provider": self.ebook_provider,
            "has_fulltext": self.has_fulltext,
            "public_scan_b": self.public_scan_b,
        }

        return cast(
            SolrDocument,
            {key: solr_doc[key] for key in solr_doc if solr_doc[key] not in (None, [], "") and key not in exclude},
        )


class EditionScorecardForSolr(EditionScorecardEvaluator):
    """Evaluates an EditionScorecard using an EditionSolrBuilder as the data source."""

    REQUIRED_SOLR_WORK_FIELDS = (
        "ddc_sort",
        "first_publish_year",
        "lcc_sort",
        "lexile",
        "ratings_count",
        "readinglog_count",
    )

    def __init__(
        self,
        solr_edition: EditionSolrBuilder,
        solr_work: SolrDocument,
        db_work: dict | None,
        authors: list[dict],
    ):
        self.solr_edition = solr_edition
        self.solr_work = solr_work
        self.db_work = db_work or {}
        self.authors = authors

    # --- Access ---

    @property
    def read_access(self) -> bool:
        return self.solr_edition.ebook_access >= bp.EbookAccess.BORROWABLE

    @property
    def search_inside_access(self) -> bool:
        return self.solr_edition.ebook_access >= bp.EbookAccess.PRINTDISABLED

    @property
    def programmatic_access(self) -> bool:
        return self.solr_edition.ebook_access == bp.EbookAccess.PUBLIC

    @property
    def purchase_options(self) -> bool:
        identifiers = self.solr_edition._edition.get("identifiers", {})
        return bool(self.solr_edition.isbn or identifiers.get("amazon") or identifiers.get("better_world_books"))

    @property
    def library_options(self) -> bool:
        return bool(self.solr_edition.isbn or self.solr_edition.oclc)

    @property
    def fan_fiction(self) -> bool:
        return any("archiveofourown.org" in (link.get("url", "") if isinstance(link, dict) else "") for link in self.db_work.get("links", []))

    @property
    def wikipedia(self) -> bool:
        return bool(self.db_work.get("identifiers", {}).get("wikidata")) or any(
            "wikipedia.org" in (link.get("url", "") if isinstance(link, dict) else "") for link in self.db_work.get("links", [])
        )

    @property
    def first_sentence(self) -> bool:
        return bool(self.solr_edition._edition.get("first_sentence"))

    # --- Discovery ---

    @property
    def title(self) -> bool:
        return bool(self.solr_edition.title)

    @property
    def author_name(self) -> bool:
        return bool(self.db_work.get("authors"))

    @property
    def genre_tags(self) -> bool:
        # Not a thing yet
        # return bool(self.solr_work.get("genres"))
        return False

    @property
    def series(self) -> bool:
        return bool(self.db_work.get("series"))

    @property
    def table_of_contents(self) -> bool:
        return bool(self.solr_edition.chapter)

    @property
    def classifications(self) -> bool:
        # Doesn't matter which edition has the classification
        return bool(self.solr_work.get("ddc_sort") or self.solr_work.get("lcc_sort"))

    @property
    def language(self) -> bool:
        return bool(self.solr_edition.language)

    @property
    def isbn(self) -> bool:
        return bool(self.solr_edition.isbn)

    @property
    def lexile(self) -> bool:
        # Doesn't matter which edition has the lexile score
        return bool(self.solr_work.get("lexile"))

    @property
    def star_ratings(self) -> bool:
        return (self.solr_work.get("ratings_count") or 0) > 0

    @property
    def on_readinglogs(self) -> bool:
        return (self.solr_work.get("readinglog_count") or 0) > 0

    @property
    def on_lists(self) -> bool:
        return False  # not yet available in Solr builder

    @property
    def contributor_names(self) -> bool:
        return bool(self.solr_edition._edition.get("contributions"))

    # --- Evaluation ---

    @property
    def basic_description(self) -> bool:
        return bool(self.solr_edition._get_description_text())

    @property
    def cover(self) -> bool:
        return bool(self.solr_edition.cover_i)

    @property
    def rich_description(self) -> bool:
        return len(self.solr_edition._get_description_text()) > 50

    @property
    def readinglog_counts(self) -> bool:
        return (self.solr_work.get("readinglog_count") or 0) > 0

    @property
    def list_count(self) -> bool:
        return False  # not yet available in Solr builder

    @property
    def page_count(self) -> bool:
        return bool(self.solr_edition.number_of_pages)

    @property
    def author_photo(self) -> bool:
        return any(p for a in self.authors for p in (a.get("photos") or []) if p != -1)

    @property
    def first_publish_year(self) -> bool:
        return bool(self.solr_work.get("first_publish_year"))

    @property
    def publish_year(self) -> bool:
        return bool(self.solr_edition.publish_year)

    @property
    def author_bio(self) -> bool:
        return any(a.get("bio") or a.get("description") for a in self.authors)

    @property
    def publisher(self) -> bool:
        return bool(self.solr_edition.publisher) and not all(is_sine_nomine(p) for p in self.solr_edition.publisher)

    @property
    def author_links(self) -> bool:
        return any(a.get("remote_ids") for a in self.authors)
