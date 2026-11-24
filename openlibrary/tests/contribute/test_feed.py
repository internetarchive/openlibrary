import threading
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from openlibrary.contribute import feed, pool
from openlibrary.core.cache import MemoryCache


class FakeThing(dict):
    def __init__(self, key, **fields):
        super().__init__(fields)
        self.key = key


class Ref:
    """A reference as infogami hands it back: a keyed Thing, or a keyless one wrapping an ``author``."""

    def __init__(self, key=None, author=None):
        self.key = key
        if author:
            self.author = author


class FakeSite:
    def __init__(self, changes, things):
        self._changes = changes
        self._things = {t.key: t for t in things}
        self.queries = []

    def recentchanges(self, query):
        assert query["bot"] is False
        # The date bounds the scan; a week back, as a day.
        assert datetime.strptime(query["begin_date"], "%Y-%m-%d").date() == (datetime.now(UTC) - timedelta(days=feed.POOL_DAYS)).date()
        self.queries.append(query)
        return [c for c in self._changes if c.kind == query["kind"]]

    def get_many(self, keys):
        return [self._things[k] for k in keys if k in self._things]


def make_change(id, kind, keys, author="/people/kate", comment=""):
    return SimpleNamespace(
        id=id,
        kind=kind,
        changes=[{"key": k, "revision": 2} for k in keys],
        author=SimpleNamespace(key=author) if author else None,
        comment=comment,
        timestamp=datetime(2026, 10, 14, 12, 0, 0),
    )


def make_site():
    return FakeSite(
        [
            make_change(6, "edit-book", ["/books/OL1M"], comment="Added page count"),
            make_change(5, "add-cover", ["/books/OL3M"], comment="//covers.openlibrary.org/b/id/7-S.jpg"),
            make_change(4, "edit-book", ["/books/OL4M"]),
            make_change(3, "add-book", ["/works/OL2W", "/books/OL2M"], author=None, comment="Added new book."),
            make_change(2, "edit-book", ["/books/OL5M"]),
        ],
        [
            FakeThing("/books/OL1M", title="Dune", covers=[-1, 42], authors=[Ref("/authors/OL1A")]),
            # No authors of its own: they come from the work.
            FakeThing("/books/OL3M", title="Emma", covers=[7], works=[Ref("/works/OL2W")]),
            # Another edition of Dune: one row per title.
            FakeThing("/books/OL4M", title="dune"),
            FakeThing("/works/OL2W", title="Emma", authors=[Ref(author=Ref("/authors/OL2A"))]),
            # No title (a deleted or broken record): skipped.
            FakeThing("/books/OL5M"),
            FakeThing("/authors/OL1A", name="Frank Herbert"),
            FakeThing("/authors/OL2A", name="Jane Austen"),
            FakeThing("/people/kate", displayname="Kate"),
        ],
    )


def test_build_pool_asks_for_each_kind_and_keeps_one_row_per_title():
    site = make_site()
    rows = feed.build_pool(site)
    assert [q["kind"] for q in site.queries] == list(feed.POOL_KINDS)
    assert [r["id"] for r in rows] == ["6", "5"]
    assert rows[0] == {
        "id": "6",
        "key": "/books/OL1M",
        "title": "Dune",
        "authors": "Frank Herbert",
        "cover_url": feed.cover_url(42),
        "kind": "edit-book",
        "editor": "Kate",
        "editor_key": "/people/kate",
        "comment": "Added page count",
    }
    assert rows[1]["authors"] == "Jane Austen"
    # Cover and new-book comments are system defaults, not the editor's words.
    assert rows[1]["comment"] == ""


def test_build_pool_falls_back_to_username_and_visitor():
    site = make_site()
    site._things.pop("/people/kate")
    site._changes = [make_change(9, "edit-book", ["/books/OL1M"]), make_change(8, "add-book", ["/books/OL3M"], author=None)]
    rows = feed.build_pool(site)
    # Anonymous editors are left blank in the shared pool and named per request.
    assert [r["editor"] for r in rows] == ["kate", ""]
    assert [r["editor"] for r in feed.rotate(rows, 2, 0, None, str)] == ["kate", "a visitor"]


def test_interleave_by_editor_spreads_one_editors_run():
    def row(id, editor_key):
        return {"id": id, "editor_key": editor_key}

    rows = [row("9", "/people/kate"), row("8", "/people/kate"), row("7", "/people/kate"), row("6", "/people/ravi"), row("5", ""), row("4", "/people/kate")]
    assert [r["id"] for r in feed.interleave_by_editor(rows)] == ["9", "6", "5", "8", "7", "4"]
    assert feed.interleave_by_editor([]) == []


def test_build_pool_interleaves_editors():
    site = make_site()
    site._changes = [
        make_change(9, "edit-book", ["/books/OL1M"]),
        make_change(8, "edit-book", ["/books/OL3M"]),
        make_change(7, "edit-book", ["/books/OL4M"], author="/people/ravi"),
    ]
    site._things["/books/OL4M"] = FakeThing("/books/OL4M", title="Persuasion")
    assert [r["id"] for r in feed.build_pool(site)] == ["9", "7", "8"]


def join_refreshes():
    for t in threading.enumerate():
        if t.name == feed.REFRESH_THREAD_NAME:
            t.join()


def use_memory_cache(monkeypatch, site=None):
    mc = MemoryCache()
    monkeypatch.setattr(pool.olcache, "get_memcache", lambda: mc)
    monkeypatch.setattr(feed, "create_site", lambda: site)
    return mc


def test_get_pool_on_a_cold_cache_serves_nothing_while_a_thread_builds_it(monkeypatch):
    mc = use_memory_cache(monkeypatch, make_site())
    assert feed.get_pool() == []
    join_refreshes()
    assert [r["id"] for r in mc.get(feed.POOL_KEY)["value"]] == ["6", "5"]
    assert mc.get(feed.POOL_LOCK_KEY) is None
    assert [r["id"] for r in feed.get_pool()] == ["6", "5"]


def test_get_pool_serves_a_stale_pool_while_a_thread_rebuilds_it(monkeypatch):
    site = make_site()
    mc = use_memory_cache(monkeypatch, site)
    mc.set(feed.POOL_KEY, {"at": 0, "value": [{"id": "1"}]})
    assert feed.get_pool() == [{"id": "1"}]
    join_refreshes()
    assert [r["id"] for r in mc.get(feed.POOL_KEY)["value"]] == ["6", "5"]
    assert mc.get(feed.POOL_LOCK_KEY) is None
    # Fresh: served from the cache, no queries.
    queries = len(site.queries)
    assert len(feed.get_pool()) == 2
    assert len(site.queries) == queries


def test_get_pool_keeps_the_old_pool_when_a_rebuild_comes_back_empty_fails_or_is_in_flight(monkeypatch):
    mc = use_memory_cache(monkeypatch)
    mc.set(feed.POOL_KEY, {"at": 0, "value": [{"id": "1"}]})
    monkeypatch.setattr(feed, "build_pool", lambda site: [])
    assert feed.get_pool() == [{"id": "1"}]
    join_refreshes()
    assert mc.get(feed.POOL_KEY)["value"] == [{"id": "1"}]
    assert mc.get(feed.POOL_LOCK_KEY) is None
    # A failure holds the lock, so the next request doesn't start another rebuild.
    monkeypatch.setattr(feed, "build_pool", lambda site: 1 / 0)
    assert feed.get_pool() == [{"id": "1"}]
    join_refreshes()
    assert mc.get(feed.POOL_KEY)["value"] == [{"id": "1"}]
    monkeypatch.setattr(feed, "build_pool", lambda site: [{"id": "2"}])
    assert feed.get_pool() == [{"id": "1"}]
    assert not any(t.name == feed.REFRESH_THREAD_NAME for t in threading.enumerate())


def test_get_pool_on_a_cold_cache_returns_nothing_when_the_rebuild_fails(monkeypatch):
    mc = use_memory_cache(monkeypatch)
    monkeypatch.setattr(feed, "build_pool", lambda site: 1 / 0)
    assert feed.get_pool() == []
    join_refreshes()
    assert mc.get(feed.POOL_KEY) is None


def test_recent_rows_rotate_the_pool_or_return_nothing(monkeypatch):
    now = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)
    pool = feed.build_pool(make_site())
    monkeypatch.setattr(feed, "get_pool", lambda: pool)
    rows = feed.recent_rows(3, offset=1, now=now)
    assert [r["id"] for r in rows] == ["5", "6", "5"]
    assert all(datetime.fromisoformat(r["timestamp"]) <= now for r in rows)
    monkeypatch.setattr(feed, "get_pool", list)
    assert feed.recent_rows(2) == []


def test_clean_comment_drops_urls_keys_and_essays():
    assert feed.clean_comment("  Added page count ") == "Added page count"
    assert feed.clean_comment("https://covers.openlibrary.org/b/id/1-S.jpg") == ""
    assert feed.clean_comment("/people/kate") == ""
    assert feed.clean_comment("x" * 91) == ""
    assert feed.clean_comment(None) == ""


def test_ref_key_reads_edition_refs_and_embedded_work_authors_without_loading():
    assert feed.ref_key(Ref("/authors/OL1A")) == "/authors/OL1A"
    assert feed.ref_key(Ref(author=Ref("/authors/OL2A"))) == "/authors/OL2A"
    assert feed.ref_key(Ref()) == ""


def test_record_key_prefers_the_book_over_authors_and_works():
    change = make_change(1, "edit-book", ["/authors/OL1A", "/works/OL1W", "/books/OL1M", "/people/kate"])
    assert feed.record_key(change) == "/books/OL1M"
    assert feed.record_key(make_change(1, "edit-book", ["/authors/OL1A", "/works/OL1W"])) == "/works/OL1W"
    assert feed.record_key(make_change(1, "edit-book", ["/people/kate"])) == ""
