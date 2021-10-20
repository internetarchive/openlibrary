from typing import Union, List, Optional

from openlibrary.book_providers import AbstractBookProvider
from openlibrary.plugins.upstream.models import Edition


class InternetArchiveProvider(AbstractBookProvider):
    short_name = 'ia'
    identifier_key = 'ocaid'

    def get_identifiers(self, ed_or_solr: Union[Edition, dict]) -> Optional[List[str]]:
        # Solr record augmented with availability
        if ed_or_solr.get('availability', {}).get('identifier'):
            return [ed_or_solr['availability']['identifier']]
        # Edition
        if ed_or_solr.get('ocaid'):
            return [ed_or_solr['ocaid']]

        # Regular solr record
        ed_or_solr.get('ia')
