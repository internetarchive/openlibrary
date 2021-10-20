from typing import Union, List, Optional

from openlibrary.app import render_template
from openlibrary.plugins.upstream.models import Edition
from openlibrary.plugins.upstream.utils import get_coverstore_public_url


class AbstractBookProvider:
    short_name: str

    """
    The key in the identifiers field on editions;
    see https://openlibrary.org/config/edition
    """
    identifier_key: str

    def get_identifiers(self, ed_or_solr: Union[Edition, dict]) -> Optional[List[str]]:
        return (
            # If it's an edition
            ed_or_solr.get('identifiers', {}).get(self.identifier_key) or
            # if it's a solr work record
            ed_or_solr.get(f'id_{self.identifier_key}')
        )

    def choose_best_identifier(self, identifiers: List[str]) -> str:
        return identifiers[0]

    def render_read_button(self, ed_or_solr: Union[Edition, dict]):
        identifiers = self.get_identifiers(ed_or_solr)
        assert identifiers

        return render_template(
            f"book_providers/{self.short_name}_read_button.html",
            self.choose_best_identifier(identifiers)
        )

    def render_download_options(
            self,
            ed_or_solr: Union[Edition, dict],
            extra_args: List = None):
        identifiers = self.get_identifiers(ed_or_solr)
        assert identifiers

        return render_template(
            f"book_providers/{self.short_name}_download_options.html",
            self.choose_best_identifier(identifiers),
            *(extra_args or [])
        )

    def get_cover_url(self, ed_or_solr: Union[Edition, dict]) -> Optional[str]:
        """
        Get the cover url most appropriate for this copy when made available by this
        provider
        """
        size = 'M'

        # Editions
        if isinstance(ed_or_solr, Edition):
            return ed_or_solr.get_cover().url(size)

        # Solr document augmented with availability
        availability = ed_or_solr.get('availability', {})

        if availability.get('openlibrary_edition'):
            olid = availability.get('openlibrary_edition')
            return f"{get_coverstore_public_url()}/b/olid/{olid}-{size}.jpg"
        if availability.get('identifier'):
            ocaid = ed_or_solr['availability']['identifier']
            return f"//archive.org/services/img/{ocaid}"

        # Plain solr - we don't know which edition is which here, so this is most
        # preferable
        if ed_or_solr.get('cover_i'):
            cover_i = ed_or_solr["cover_i"]
            return f'{get_coverstore_public_url()}/b/id/{cover_i}-{size}.jpg'
        if ed_or_solr.get('cover_edition_key'):
            olid = ed_or_solr['cover_edition_key']
            return f"{get_coverstore_public_url()}/b/olid/{olid}-{size}.jpg"
        if ed_or_solr.get('ocaid'):
            # TODO: Should I be using //archive.org/download/%s/page/cover_w60_h60.jpg
            #  instead?
            return f"//archive.org/services/img/{ed_or_solr.get('ocaid')}"

        # No luck
        return None
