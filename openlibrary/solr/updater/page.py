from typing import cast

from openlibrary.solr.solr_types import SolrDocument
from openlibrary.solr.updater.abstract import AbstractSolrBuilder, AbstractSolrUpdater
from openlibrary.solr.utils import SolrUpdateRequest


class PageSolrUpdater(AbstractSolrUpdater):
    key_prefix = "/"
    thing_type = "/type/page"

    def key_test(self, key: str) -> bool:
        EXCLUDED = (
            "/type/",
            "/works/",
            "/books/",
            "/authors/",
            "/people/",
            "/lists/",
            "/series/",
            "/subjects/",
            "/languages/",
            "/publishers/",
            "/collections/",
            "/search",
            "/admin",
        )
        return key.startswith("/") and not any(key.startswith(p) for p in EXCLUDED)

    async def update_key(self, thing: dict) -> tuple[SolrUpdateRequest, list[str]]:
        if thing.get("type", {}).get("key") != "/type/page":
            return SolrUpdateRequest(), []
        doc = PageSolrBuilder(thing).build()
        return SolrUpdateRequest(adds=[doc]), []


class PageSolrBuilder(AbstractSolrBuilder):
    def __init__(self, page: dict):
        self._page = page

    @property
    def key(self) -> str:
        return self._page["key"]

    @property
    def type(self) -> str:
        return "page"

    @property
    def title(self) -> str | None:
        return self._page.get("title")

    @property
    def body(self) -> str | None:
        body = self._page.get("body")
        if isinstance(body, dict):
            return body.get("value")
        return body

    @property
    def last_modified(self) -> str | None:
        last_mod = self._page.get("last_modified")
        if isinstance(last_mod, dict):
            value = last_mod.get("value")
            return (value + "Z") if value and not value.endswith("Z") else value
        elif isinstance(last_mod, str):
            return last_mod if last_mod.endswith("Z") else last_mod + "Z"
        return None

    def build(self) -> SolrDocument:
        return cast(SolrDocument, super().build())
