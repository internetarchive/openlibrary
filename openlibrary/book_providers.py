from typing import List, Optional, Union, Literal

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

    def get_template_path(self, typ: Literal['read_button', 'download_options']) -> str:
        return f"book_providers/{self.short_name}_{typ}.html"

    def render_read_button(self, ed_or_solr: Union[Edition, dict]):
        identifiers = self.get_identifiers(ed_or_solr)
        assert identifiers

        return render_template(
            self.get_template_path('read_button'),
            self.choose_best_identifier(identifiers)
        )

    def render_download_options(self, edition: Edition, extra_args: List = None):
        identifiers = self.get_identifiers(edition)
        assert identifiers

        return render_template(
            self.get_template_path('download_options'),
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
            return f"//archive.org/services/img/{ed_or_solr.get('ocaid')}"

        # No luck
        return None

    def is_own_ocaid(self, ocaid: str) -> bool:
        """Whether the ocaid is an archive of content from this provider"""
        return False


class InternetArchiveProvider(AbstractBookProvider):
    short_name = 'ia'
    identifier_key = 'ocaid'

    def get_identifiers(self, ed_or_solr: Union[Edition, dict]) -> Optional[List[str]]:
        # Solr work record augmented with availability
        if ed_or_solr.get('availability', {}).get('identifier'):
            return [ed_or_solr['availability']['identifier']]

        # Edition
        if ed_or_solr.get('ocaid'):
            return [ed_or_solr['ocaid']]

        # Solr work record
        return ed_or_solr.get('ia')

    def is_own_ocaid(self, ocaid: str) -> bool:
        return True

    def render_download_options(self, edition: Edition, extra_args: List = None):
        if not edition.is_access_restricted() and edition.ia_metadata:
            # This needs access to the full edition
            return render_template(self.get_template_path('download_options'), edition)
        else:
            return ''


class LibriVoxProvider(AbstractBookProvider):
    short_name = 'librivox'
    identifier_key = 'librivox'

    def render_download_options(self, edition: Edition, extra_args: List = None):
        # The template also needs the ocaid, since some of the files are hosted on IA
        return super().render_download_options(edition, [edition.get('ocaid')])

    def is_own_ocaid(self, ocaid: str) -> bool:
        return 'librivox' in ocaid


class ProjectGutenbergProvider(AbstractBookProvider):
    short_name = 'gutenberg'
    identifier_key = 'project_gutenberg'

    def is_own_ocaid(self, ocaid: str) -> bool:
        return ocaid.endswith('gut')


class StandardEbooksProvider(AbstractBookProvider):
    short_name = 'standard_ebooks'
    identifier_key = 'standard_ebooks'

    def is_own_ocaid(self, ocaid: str) -> bool:
        # Standard ebooks isn't archived on IA
        return False


PROVIDER_ORDER: List[AbstractBookProvider] = [
    # These providers act essentially as their own publishers, so link to the first when
    # we're on an edition page
    LibriVoxProvider(),
    ProjectGutenbergProvider(),
    StandardEbooksProvider(),
    # Then link to IA
    InternetArchiveProvider(),
]


def is_non_ia_ocaid(ocaid: str) -> bool:
    """
    Check if the ocaid "looks like" it's from another provider
    """
    providers = (
        provider
        for provider in PROVIDER_ORDER
        if provider.short_name != 'ia')
    return any(
        provider.is_own_ocaid(ocaid)
        for provider in providers)


def get_book_provider(
        ed_or_solr: Union[Edition, dict]
) -> Optional[AbstractBookProvider]:
    # On edition pages, we prefer non-IA resources, because on those
    # pages, IA is just archiving the original's content
    if isinstance(ed_or_solr, Edition):
        for provider in PROVIDER_ORDER:
            if provider.get_identifiers(ed_or_solr):
                return provider

    # On search results, we want to display IA copies first.
    # Issue is that an edition can be provided by multiple providers; we can easily
    # choose the correct copy when on an edition, but on a solr record, with all copies
    # of all editions aggregated, it's more difficult.
    # So we do some ugly ocaid sniffing to try to guess :/ Idea being that we ignore
    # OCAIDs that look like they're from other providers.
    ia_ocaids = [
        ocaid
        # For some reason ia was explicitly None sometimes
        for ocaid in (ed_or_solr.get('ia', []) or [])
        if not is_non_ia_ocaid(ocaid)
    ]

    if ia_ocaids:
        return PROVIDER_ORDER[-1]
    else:
        # No IA-only ocaids, so now we do the normal flow
        for provider in PROVIDER_ORDER:
            if provider.get_identifiers(ed_or_solr):
                return provider

        # No luck
        return None


setattr(get_book_provider, 'ia', PROVIDER_ORDER[-1])
