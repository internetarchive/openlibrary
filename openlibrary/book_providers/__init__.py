from typing import List, Optional, Union

from openlibrary.book_providers.AbstractBookProvider import AbstractBookProvider
from openlibrary.book_providers.InternetArchiveProvider import InternetArchiveProvider
from openlibrary.book_providers.LibriVoxProvider import LibriVoxProvider
from openlibrary.book_providers.ProjectGutenbergProvider import ProjectGutenbergProvider
from openlibrary.book_providers.StandardEbooksProvider import StandardEbooksProvider
from openlibrary.plugins.upstream.models import Edition

PROVIDER_ORDER: List[AbstractBookProvider] = [
    LibriVoxProvider(),
    ProjectGutenbergProvider(),
    StandardEbooksProvider(),
    InternetArchiveProvider(),
]


def get_book_provider(
        ed_or_solr: Union[Edition, dict]
) -> Optional[AbstractBookProvider]:
    for provider in PROVIDER_ORDER:
        if provider.get_identifiers(ed_or_solr):
            return provider
    return None


setattr(get_book_provider, 'ia', InternetArchiveProvider)
