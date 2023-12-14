from functools import cached_property
import logging
import re
from typing import cast

import openlibrary.book_providers as bp
from openlibrary.solr.solr_types import SolrDocument
from openlibrary.solr.utils import get_solr_next
from openlibrary.utils import uniq
from openlibrary.utils.isbn import opposite_isbn


logger = logging.getLogger("openlibrary.solr")


re_lang_key = re.compile(r'^/(?:l|languages)/([a-z]{3})$')
re_year = re.compile(r'\b(\d{4})\b')
re_solr_field = re.compile(r'^[-\w]+$', re.U)
re_not_az = re.compile('[^a-zA-Z]')


def is_sine_nomine(pub: str) -> bool:
    """Check if the publisher is 'sn' (excluding non-letter characters)."""
    return re_not_az.sub('', pub).lower() == 'sn'


class EditionSolrBuilder:
    def __init__(self, edition: dict, ia_metadata: bp.IALiteMetadata | None = None):
        self.edition = edition
        self.ia_metadata = ia_metadata
        self.provider = bp.get_book_provider(edition)

    def get(self, key: str, default=None):
        return self.edition.get(key, default)

    @property
    def key(self):
        return self.edition['key']

    @property
    def title(self) -> str | None:
        return self.get('title')

    @property
    def subtitle(self) -> str | None:
        return self.get('subtitle')

    @property
    def alternative_title(self) -> set[str]:
        """Get titles from the editions as alternative titles."""
        result: set[str] = set()
        full_title = self.get('title')
        if not full_title:
            return result
        if self.get('subtitle'):
            full_title += ': ' + self.get('subtitle')
        result.add(full_title)
        result.update(self.get('work_titles', []))
        result.update(self.get('other_titles', []))

        return result

    @property
    def cover_i(self) -> int | None:
        return next(
            (cover_id for cover_id in self.get('covers', []) if cover_id != -1), None
        )

    @property
    def languages(self) -> list[str]:
        """Gets the 3 letter language codes (eg ['ger', 'fre'])"""
        result: list[str] = []
        for lang in self.get('languages', []):
            m = re_lang_key.match(lang['key'] if isinstance(lang, dict) else lang)
            if m:
                result.append(m.group(1))
        return uniq(result)

    @property
    def publisher(self) -> list[str]:
        return uniq(
            publisher if not is_sine_nomine(publisher) else 'Sine nomine'
            for publisher in self.get('publishers', [])
        )

    @property
    def number_of_pages(self) -> int | None:
        try:
            return int(self.get('number_of_pages')) or None
        except (TypeError, ValueError):  # int(None) -> TypeErr, int("vii") -> ValueErr
            return None

    @property
    def format(self) -> str | None:
        return self.get('physical_format')

    @property
    def isbn(self) -> list[str]:
        """
        Get all ISBNs of the given edition. Calculates complementary ISBN13 for each
        ISBN10 and vice-versa. Does not remove '-'s.
        """
        isbns = []

        isbns += [isbn.replace("_", "").strip() for isbn in self.get("isbn_13", [])]
        isbns += [isbn.replace("_", "").strip() for isbn in self.get("isbn_10", [])]

        # Get the isbn13 when isbn10 is present and vice-versa.
        isbns += [opposite_isbn(v) for v in isbns]

        return uniq(isbn for isbn in isbns if isbn)

    @property
    def lccn(self) -> list[str]:
        return uniq(lccn.strip() for lccn in self.get('lccn', []))

    @property
    def publish_date(self) -> str | None:
        return self.get('publish_date')

    @property
    def publish_year(self) -> int | None:
        if self.publish_date:
            m = re_year.search(self.publish_date)
            return int(m.group(1)) if m else None
        else:
            return None

    @property
    def ia(self) -> str | None:
        ocaid = self.get('ocaid')
        return ocaid.strip() if ocaid else None

    @property
    def ia_collection(self) -> list[str]:
        collections = self.ia_metadata['collection'] if self.ia_metadata else set()
        # Exclude fav-* collections because they're not useful to us.
        return [c for c in collections if not c.startswith('fav-')]

    @property
    def ia_box_id(self) -> list[str]:
        boxids = []
        if 'ia_box_id' in self.edition:
            if isinstance(self.edition['ia_box_id'], str):
                boxids = [self.edition['ia_box_id']]
            elif isinstance(self.edition['ia_box_id'], list):
                boxids = self.edition['ia_box_id']
            else:
                logger.warning(
                    f'Bad ia_box_id on {self.key}: "{self.edition["ia_box_id"]}"'
                )
        if self.ia_metadata:
            boxids += list(self.ia_metadata.get('boxid') or [])

        return uniq(boxids, key=lambda x: x.lower())

    @property
    def identifiers(self) -> dict:
        identifiers = {}
        for key, id_list in self.get('identifiers', {}).items():
            solr_key = (
                key.replace('.', '_')
                .replace(',', '_')
                .replace('(', '')
                .replace(')', '')
                .replace(':', '_')
                .replace('/', '')
                .replace('#', '')
                .lower()
            )
            m = re_solr_field.match(solr_key)
            if not m:
                logger.warning(f'Bad identifier on {self.key}: "{key}"')
                continue

            identifiers[f'id_{solr_key}'] = uniq(v.strip() for v in id_list)
        return identifiers

    @cached_property
    def ebook_access(self) -> bp.EbookAccess:
        if not self.provider:
            return bp.EbookAccess.NO_EBOOK
        elif isinstance(self.provider, bp.InternetArchiveProvider):
            return self.provider.get_access(self.edition, self.ia_metadata)
        else:
            return self.provider.get_access(self.edition)

    @property
    def has_fulltext(self) -> bool:
        return self.ebook_access > bp.EbookAccess.UNCLASSIFIED

    @property
    def public_scan_b(self) -> bool:
        return self.ebook_access == bp.EbookAccess.PUBLIC


def build_edition_data(
    edition: dict,
    ia_metadata: bp.IALiteMetadata | None = None,
) -> SolrDocument:
    """
    Build the solr document for the given edition to store as a nested
    document
    """

    ed = EditionSolrBuilder(edition, ia_metadata)
    solr_doc: SolrDocument = cast(
        SolrDocument,
        {
            'key': ed.key,
            'type': 'edition',
            # Display data
            'title': ed.title,
            'subtitle': ed.subtitle,
            'alternative_title': list(ed.alternative_title),
            'cover_i': ed.cover_i,
            'language': ed.languages,
            # Misc useful data
            'publisher': ed.publisher,
            **(
                {'format': [ed.format] if ed.format else None}
                if get_solr_next()
                else {}
            ),
            'publish_date': [ed.publish_date] if ed.publish_date else None,
            'publish_year': [ed.publish_year] if ed.publish_year else None,
            # Identifiers
            'isbn': ed.isbn,
            'lccn': ed.lccn,
            **ed.identifiers,
            # IA
            'ia': [ed.ia] if ed.ia else None,
            'ia_collection': ed.ia_collection,
            'ia_box_id': ed.ia_box_id,
            # Ebook access
            'ebook_access': ed.ebook_access.to_solr_str(),
            'has_fulltext': ed.has_fulltext,
            'public_scan_b': ed.public_scan_b,
        },
    )

    return cast(
        SolrDocument,
        {
            key: solr_doc[key]  # type: ignore
            for key in solr_doc
            if solr_doc[key] not in (None, [], '')  # type: ignore
        },
    )
