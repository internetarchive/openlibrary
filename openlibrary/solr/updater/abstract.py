from collections.abc import Iterable
from openlibrary.solr.utils import SolrUpdateRequest


class AbstractSolrUpdater:
    key_prefix: str
    thing_type: str

    def key_test(self, key: str) -> bool:
        return key.startswith(self.key_prefix)

    async def preload_keys(self, keys: Iterable[str]):
        from openlibrary.solr.update_work import data_provider

        await data_provider.preload_documents(keys)

    async def update_key(self, thing: dict) -> tuple[SolrUpdateRequest, list[str]]:
        """
        :return: (update, new keys to update)
        """
        raise NotImplementedError()
