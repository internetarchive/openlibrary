from typing import TypedDict, Literal, cast, TypeVar, Generic
from collections.abc import Callable, Iterator

import web
from web import uniq

from openlibrary.app import render_template
from openlibrary.plugins.upstream.models import Edition
from openlibrary.plugins.upstream.utils import get_coverstore_public_url
from openlibrary.utils import OrderedEnum, multisort_best


class EbookAccess(OrderedEnum):
    # Keep in sync with solr/conf/enumsConfig.xml !
    NO_EBOOK = 0
    UNCLASSIFIED = 1
    PRINTDISABLED = 2
    BORROWABLE = 3
    PUBLIC = 4

    def to_solr_str(self):
        return self.name.lower()


class IALiteMetadata(TypedDict):
    boxid: set[str]
    collection: set[str]
    access_restricted_item: Literal['true', 'false'] | None


TProviderMetadata = TypeVar('TProviderMetadata')


class AbstractBookProvider(Generic[TProviderMetadata]):
    short_name: str

    """
    The key in the identifiers field on editions;
    see https://openlibrary.org/config/edition
    """
    identifier_key: str

    def get_olids(self, identifier):
        return web.ctx.site.things(
            {"type": "/type/edition", self.db_selector: identifier}
        )

    @property
    def editions_query(self):
        return {f"{self.db_selector}~": "*"}

    @property
    def db_selector(self):
        return f"identifiers.{self.identifier_key}"

    @property
    def solr_key(self):
        return f"id_{self.identifier_key}"

    def get_identifiers(self, ed_or_solr: Edition | dict) -> list[str]:
        return (
            # If it's an edition
            ed_or_solr.get('identifiers', {}).get(self.identifier_key, [])
            or
            # if it's a solr work record
            ed_or_solr.get(f'id_{self.identifier_key}', [])
        )

    def choose_best_identifier(self, identifiers: list[str]) -> str:
        return identifiers[0]

    def get_best_identifier(self, ed_or_solr: Edition | dict) -> str:
        identifiers = self.get_identifiers(ed_or_solr)
        assert identifiers
        return self.choose_best_identifier(identifiers)

    def get_best_identifier_slug(self, ed_or_solr: Edition | dict) -> str:
        """Used in eg /work/OL1W?edition=ia:foobar URLs, for example"""
        return f'{self.short_name}:{self.get_best_identifier(ed_or_solr)}'

    def get_template_path(self, typ: Literal['read_button', 'download_options']) -> str:
        return f"book_providers/{self.short_name}_{typ}.html"

    def render_read_button(
        self, ed_or_solr: Edition | dict, analytics_attr: Callable[[str], str]
    ):
        return render_template(
            self.get_template_path('read_button'),
            self.get_best_identifier(ed_or_solr),
            analytics_attr,
        )

    def render_download_options(self, edition: Edition, extra_args: list | None = None):
        return render_template(
            self.get_template_path('download_options'),
            self.get_best_identifier(edition),
            *(extra_args or []),
        )

    def is_own_ocaid(self, ocaid: str) -> bool:
        """Whether the ocaid is an archive of content from this provider"""
        return False

    def get_access(
        self,
        edition: dict,
        metadata: TProviderMetadata | None = None,
    ) -> EbookAccess:
        """
        Return the access level of the edition.
        """
        # Most providers are for public-only ebooks right now
        return EbookAccess.PUBLIC


class InternetArchiveProvider(AbstractBookProvider[IALiteMetadata]):
    short_name = 'ia'
    identifier_key = 'ocaid'

    @property
    def db_selector(self):
        return self.identifier_key

    @property
    def solr_key(self):
        return "ia"

    def get_identifiers(self, ed_or_solr: Edition | dict) -> list[str]:
        # Solr work record augmented with availability
        # Sometimes it's set explicitly to None, for some reason
        availability = ed_or_solr.get('availability', {}) or {}
        if availability.get('identifier'):
            return [ed_or_solr['availability']['identifier']]

        # Edition
        if ed_or_solr.get('ocaid'):
            return [ed_or_solr['ocaid']]

        # Solr work record
        return ed_or_solr.get('ia', [])

    def is_own_ocaid(self, ocaid: str) -> bool:
        return True

    def render_download_options(self, edition: Edition, extra_args: list | None = None):
        if edition.is_access_restricted():
            return ''

        formats = {
            'pdf': edition.get_ia_download_link('.pdf'),
            'epub': edition.get_ia_download_link('.epub'),
            'mobi': edition.get_ia_download_link('.mobi'),
            'txt': edition.get_ia_download_link('_djvu.txt'),
        }

        if any(formats.values()):
            return render_template(
                self.get_template_path('download_options'),
                formats,
                edition.url('/daisy'),
            )
        else:
            return ''

    def get_access(
        self, edition: dict, metadata: IALiteMetadata | None = None
    ) -> EbookAccess:
        if not metadata:
            if edition.get('ocaid'):
                return EbookAccess.UNCLASSIFIED
            else:
                return EbookAccess.NO_EBOOK

        collections = metadata.get('collection', set())
        access_restricted_item = metadata.get('access_restricted_item') == "true"

        if 'inlibrary' in collections:
            return EbookAccess.BORROWABLE
        elif 'printdisabled' in collections:
            return EbookAccess.PRINTDISABLED
        elif access_restricted_item or not collections:
            return EbookAccess.UNCLASSIFIED
        else:
            return EbookAccess.PUBLIC


class LibriVoxProvider(AbstractBookProvider):
    short_name = 'librivox'
    identifier_key = 'librivox'

    def render_download_options(self, edition: Edition, extra_args: list | None = None):
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


class OpenStaxProvider(AbstractBookProvider):
    short_name = 'openstax'
    identifier_key = 'openstax'

    def is_own_ocaid(self, ocaid: str) -> bool:
        return False


class CitaPressProvider(AbstractBookProvider):
    short_name = 'cita_press'
    identifier_key = 'cita_press'

    def is_own_ocaid(self, ocaid: str) -> bool:
        return False


PROVIDER_ORDER: list[AbstractBookProvider] = [
    # These providers act essentially as their own publishers, so link to the first when
    # we're on an edition page
    LibriVoxProvider(),
    ProjectGutenbergProvider(),
    StandardEbooksProvider(),
    OpenStaxProvider(),
    CitaPressProvider(),
    # Then link to IA
    InternetArchiveProvider(),
]


def get_cover_url(ed_or_solr: Edition | dict) -> str | None:
    """
    Get the cover url most appropriate for this edition or solr work search result
    """
    size = 'M'

    # Editions
    if isinstance(ed_or_solr, Edition):
        cover = ed_or_solr.get_cover()
        return cover.url(size) if cover else None

    # Solr edition
    elif ed_or_solr['key'].startswith('/books/'):
        if ed_or_solr.get('cover_i'):
            return (
                get_coverstore_public_url()
                + f'/b/id/{ed_or_solr["cover_i"]}-{size}.jpg'
            )
        else:
            return None

    # Solr document augmented with availability
    availability = ed_or_solr.get('availability', {}) or {}

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


def is_non_ia_ocaid(ocaid: str) -> bool:
    """
    Check if the ocaid "looks like" it's from another provider
    """
    providers = (provider for provider in PROVIDER_ORDER if provider.short_name != 'ia')
    return any(provider.is_own_ocaid(ocaid) for provider in providers)


def get_book_provider_by_name(short_name: str) -> AbstractBookProvider | None:
    return next((p for p in PROVIDER_ORDER if p.short_name == short_name), None)


ia_provider = cast(InternetArchiveProvider, get_book_provider_by_name('ia'))
prefer_ia_provider_order = uniq([ia_provider, *PROVIDER_ORDER])


def get_provider_order(prefer_ia=False) -> list[AbstractBookProvider]:
    default_order = prefer_ia_provider_order if prefer_ia else PROVIDER_ORDER

    provider_order = default_order
    provider_overrides = None
    # Need this to work in test environments
    if 'env' in web.ctx:
        provider_overrides = web.input(providerPref=None, _method='GET').providerPref
    if provider_overrides:
        new_order: list[AbstractBookProvider] = []
        for name in provider_overrides.split(','):
            if name == '*':
                new_order += default_order
            else:
                provider = get_book_provider_by_name(name)
                if not provider:
                    # TODO: Show the user a warning somehow
                    continue
                new_order.append(provider)
        new_order = uniq(new_order + default_order)
        if new_order:
            provider_order = new_order

    return provider_order


def get_book_providers(ed_or_solr: Edition | dict) -> Iterator[AbstractBookProvider]:
    # On search results which don't have an edition selected, we want to display
    # IA copies first.
    # Issue is that an edition can be provided by multiple providers; we can easily
    # choose the correct copy when on an edition, but on a solr work record, with all
    # copies of all editions aggregated, it's more difficult.
    # So we do some ugly ocaid sniffing to try to guess :/ Idea being that we ignore
    # OCAIDs that look like they're from other providers.
    has_edition = isinstance(ed_or_solr, Edition) or ed_or_solr['key'].startswith(
        '/books/'
    )
    prefer_ia = not has_edition
    if prefer_ia:
        ia_ocaids = [
            ocaid
            # Subjects/publisher pages have ia set to a specific value :/
            for ocaid in uniq(ia_provider.get_identifiers(ed_or_solr) or [])
            if not is_non_ia_ocaid(ocaid)
        ]
        prefer_ia = bool(ia_ocaids)

    provider_order = get_provider_order(prefer_ia)
    for provider in provider_order:
        if provider.get_identifiers(ed_or_solr):
            yield provider


def get_book_provider(ed_or_solr: Edition | dict) -> AbstractBookProvider | None:
    return next(get_book_providers(ed_or_solr), None)


def get_best_edition(
    editions: list[Edition],
) -> tuple[Edition | None, AbstractBookProvider | None]:
    provider_order = get_provider_order(True)

    # Map provider name to position/ranking
    provider_rank_lookup: dict[AbstractBookProvider | None, int] = {
        provider: i for i, provider in enumerate(provider_order)
    }

    # Here, we prefer the ia editions
    augmented_editions = [(edition, get_book_provider(edition)) for edition in editions]

    best = multisort_best(
        augmented_editions,
        [
            # Prefer the providers closest to the top of the list
            ('min', lambda rec: provider_rank_lookup.get(rec[1], float('inf'))),
            # Prefer the editions with the most fields
            ('max', lambda rec: len(dict(rec[0]))),
            # TODO: Language would go in this queue somewhere
        ],
    )

    return best if best else (None, None)


def get_solr_keys():
    return [p.solr_key for p in PROVIDER_ORDER]


setattr(get_book_provider, 'ia', get_book_provider_by_name('ia'))  # noqa: B010
