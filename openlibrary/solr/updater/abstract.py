from collections.abc import Iterable
from openlibrary.solr.data_provider import DataProvider
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
        raise NotImplementedError()
