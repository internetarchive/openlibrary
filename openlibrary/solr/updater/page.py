from openlibrary.solr.solr_types import SolrDocument
from openlibrary.solr.updater.abstract import AbstractSolrBuilder, AbstractSolrUpdater
from openlibrary.solr.utils import SolrUpdateRequest


class PageSolrUpdater(AbstractSolrUpdater):
    key_prefix = "/"
    thing_type = "/type/page"

    def key_test(self, key: str) -> bool:
        # Exclude all known non-page key prefixes. The type check in
        # update_key() is the authoritative guard; this is a fast pre-filter.
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
            value = last_mod["value"]
            return value if value.endswith("Z") else value + "Z"
        elif isinstance(last_mod, str):
            return last_mod if last_mod.endswith("Z") else last_mod + "Z"
        return None

    def build(self) -> SolrDocument:
        doc: SolrDocument = {
            "key": self.key,
            "type": self.type,
        }
        if self.title is not None:
            doc["title"] = self.title
        if self.body is not None:
            doc["body"] = self.body
        if self.last_modified is not None:
            doc["last_modified"] = self.last_modified
        return doc
