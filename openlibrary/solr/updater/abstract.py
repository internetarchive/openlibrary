from collections.abc import Iterable
from typing import cast

import openlibrary.book_providers as bp
from openlibrary.solr.data_provider import DataProvider
from openlibrary.solr.solr_types import SolrDocument
from openlibrary.solr.utils import SolrUpdateRequest


class AbstractSolrUpdater:
    key_prefix: str
    thing_type: str
    data_provider: DataProvider

    def __init__(self, data_provider: DataProvider):
        self.data_provider = data_provider

    def key_test(self, key: str) -> bool:
        return key.startswith(self.key_prefix)

    async def preload_keys(self, keys: Iterable[str]):
        await self.data_provider.preload_documents(keys)

    async def update_key(self, thing: dict) -> tuple[SolrUpdateRequest, list[str]]:
        """
        :return: (update, new keys to update)
        """
        raise NotImplementedError


class AbstractSolrBuilder:
    def build(self) -> SolrDocument:
        # Iterate over all non-_ properties of this instance and add them to the
        # document.
        # Allow @property and @cached_property though!
        doc: dict = {}
        for field in dir(self):
            if field.startswith('_'):
                continue
            val = getattr(self, field)

            if callable(val):
                continue
            elif val is None or (isinstance(val, Iterable) and not val):
                # Skip if empty list/string
                continue
            elif isinstance(val, set):
                doc[field] = list(val)
            elif isinstance(val, bp.EbookAccess):
                doc[field] = val.to_solr_str()
            elif isinstance(val, (str, int, float, bool, list)):
                doc[field] = val
            else:
                raise ValueError(f'Unknown type for {field}: {type(val)}')

        return cast(SolrDocument, doc)
