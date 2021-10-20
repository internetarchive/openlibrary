from typing import Union, List, Optional

from openlibrary.book_providers import AbstractBookProvider
from openlibrary.plugins.upstream.models import Edition


class LibriVoxProvider(AbstractBookProvider):
    short_name = 'librivox'
    identifier_key = 'librivox'

    def render_download_options(
            self,
            ed_or_solr: Union[Edition, dict],
            extra_args: List = None
    ):
        return super().render_download_options(ed_or_solr, [ed_or_solr.get('ocaid')])
