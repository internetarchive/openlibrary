from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
import web

from openlibrary.contribute import initiatives, supply, tasks


class FakeStore(dict):
    def values(self, type=None, limit=100):
        return [doc for doc in dict.values(self) if doc.get("type") == type][:limit]


class FakeEdition(dict):
    def __init__(self, key, type_key="/type/edition", **fields):
        super().__init__(**fields)
        self.key = key
        self.type = web.storage(key=type_key)


class FakeWork(dict):
    def __init__(self, key, **fields):
        super().__init__(**fields)
        self.key = key
        self.type = web.storage(key="/type/work")


NONFICTION = "/tags/OL9T"
WORK = FakeWork("/works/OL1W", literary_forms=[{"key": "/tags/OL1T"}], genres=[{"key": "/tags/OL2T"}])


class FakeSite:
    def __init__(self, editions=(), store=None, works=(WORK,)):
        self.editions = {e.key: e for e in editions} | {w.key: w for w in works}
        self.store = FakeStore(store or {})

    def get_many(self, keys):
        return [self.editions[k] for k in keys if k in self.editions]


COMPLETE = {"covers": [1], "lccn": ["1"], "oclc_numbers": ["1"], "languages": ["eng"], "number_of_pages": 300, "publishers": ["P"], "works": [WORK]}
FOUR = ("covers", "languages", "number_of_pages", "publishers")


@pytest.fixture(autouse=True)
def nonfiction_by_key(monkeypatch):
    monkeypatch.setattr(tasks, "is_nonfiction", lambda work: work.get("literary_forms") == [NONFICTION])


def make_initiative(picks, calls=None, fields=FOUR):
    def pick(size, site):
        if calls is not None:
            calls.append(size)
        return picks[:size]

    return initiatives.Initiative("test", 3, pick, fields)


def test_the_initiatives_have_their_own_slugs_and_fields_tasks_knows():
    assert len({i.slug for i in initiatives.BUILTIN}) == len(initiatives.BUILTIN)
    for initiative in initiatives.BUILTIN:
        assert set(initiative.fields) <= set(tasks.POINTS)
        assert initiatives.get(initiative.slug) is initiative
    assert initiatives.get("not-an-initiative") is None
    assert initiatives.headline() is initiatives.MOST_READ
    assert initiatives.TAGS.fields == ("literary_forms", "genres")


def test_the_first_load_picks_and_stores_the_list_and_later_loads_read_it_back():
    calls = []
    initiative = make_initiative([["/books/OL1M", 5]], calls)
    site = FakeSite()
    assert initiatives.load_or_freeze(initiative, site) == [["/books/OL1M", 5]]
    assert site.store["contribute-initiative-test"]["editions"] == [["/books/OL1M", 5]]
    assert initiatives.load_or_freeze(initiative, site) == [["/books/OL1M", 5]]
    assert calls == [3]


def test_an_empty_pick_is_not_frozen():
    site = FakeSite()
    assert initiatives.load_or_freeze(make_initiative([]), site) == []
    assert "contribute-initiative-test" not in site.store


def test_gaps_list_open_fields_and_set_aside_ones_nobody_could_find():
    site = FakeSite(
        editions=[
            FakeEdition("/books/OL1M", **(COMPLETE | {"lccn": [], "publishers": []})),
            FakeEdition("/books/OL2M", **COMPLETE),
            FakeEdition("/books/OL3M", type_key="/type/redirect"),
        ],
        store={
            "contribute-initiative-test": {"editions": [["/books/OL1M", 9], ["/books/OL2M", 8], ["/books/OL3M", 7]]},
            "a": {"type": initiatives.NOT_FOUND_TYPE, "edition": "/books/OL1M", "field": "lccn", "people": ["/people/a", "/people/b"]},
            "b": {"type": initiatives.NOT_FOUND_TYPE, "edition": "/books/OL1M", "field": "publishers", "people": ["/people/a"]},
        },
    )
    gaps = initiatives.build_gaps(make_initiative([]), site)
    assert gaps == [["/books/OL1M", 9, ["publishers"], ["lccn"]], ["/books/OL2M", 8, [], []]]
    # 2 editions x 4 fields = 8 details, 1 still open: 7/8 filled, rounded down. The unfound LCCN isn't one of the fields, so it doesn't count.
    assert initiatives.progress(gaps, FOUR) == {"done": 1, "total": 2, "open": 1, "not_found": 0, "percent": 87}


def test_a_work_level_gap_is_read_from_the_edition_s_work():
    bare = FakeWork("/works/OL2W")
    site = FakeSite(
        editions=[FakeEdition("/books/OL1M", **(COMPLETE | {"works": [bare]}))],
        works=(bare,),
        store={"contribute-initiative-test": {"editions": [["/books/OL1M", 9]]}},
    )
    assert initiatives.build_gaps(make_initiative([]), site) == [["/books/OL1M", 9, ["literary_forms", "genres"], []]]


def test_a_nonfiction_work_has_no_genre_gap():
    nonfiction = FakeWork("/works/OL2W", literary_forms=[NONFICTION])
    site = FakeSite(
        editions=[FakeEdition("/books/OL1M", **(COMPLETE | {"works": [nonfiction]}))],
        works=(nonfiction,),
        store={"contribute-initiative-test": {"editions": [["/books/OL1M", 9]]}},
    )
    assert initiatives.build_gaps(make_initiative([]), site) == [["/books/OL1M", 9, [], []]]


def test_progress_counts_only_the_initiative_s_fields():
    gaps = [["/books/OL1M", 9, ["literary_forms"], []], ["/books/OL2M", 8, ["publishers"], ["literary_forms"]]]
    assert initiatives.progress(gaps, ("publishers", "covers")) == {"done": 1, "total": 2, "open": 1, "not_found": 0, "percent": 75}
    assert initiatives.progress(gaps, initiatives.TAGS.fields) == {"done": 1, "total": 2, "open": 1, "not_found": 1, "percent": 75}
    assert initiatives.progress(gaps, tuple(tasks.POINTS))["open"] == 2


def test_progress_leaves_out_fields_the_initiative_does_not_ask_about():
    gaps = [["/books/OL1M", 9, ["lccn", "oclc_numbers"], []], ["/books/OL2M", 8, ["covers"], ["oclc_numbers"]]]
    assert initiatives.progress(gaps, FOUR) == {"done": 1, "total": 2, "open": 1, "not_found": 0, "percent": 87}


def test_every_task_field_has_a_not_found_threshold():
    assert set(initiatives.NOT_FOUND_PEOPLE) == set(tasks.POINTS)


def test_fields_books_nearly_always_have_need_more_people_to_set_aside():
    people = ["/people/a", "/people/b", "/people/c", "/people/d"]
    site = FakeSite(
        store={
            "a": {"type": initiatives.NOT_FOUND_TYPE, "edition": "/books/OL1M", "field": "covers", "people": people[:2]},
            "b": {"type": initiatives.NOT_FOUND_TYPE, "edition": "/books/OL1M", "field": "publishers", "people": people[:3]},
            "c": {"type": initiatives.NOT_FOUND_TYPE, "edition": "/books/OL1M", "field": "languages", "people": people[:3]},
            "d": {"type": initiatives.NOT_FOUND_TYPE, "edition": "/books/OL2M", "field": "languages", "people": people},
            # A mark left by a field that is no longer on offer.
            "e": {"type": initiatives.NOT_FOUND_TYPE, "edition": "/books/OL2M", "field": "dewey_decimal_class", "people": people},
        },
    )
    assert initiatives.not_found_fields(site) == {"/books/OL1M": {"publishers"}, "/books/OL2M": {"languages"}}


def test_not_found_counts_each_person_once():
    site = FakeSite()
    for user in ["/people/a", "/people/a", "/people/b"]:
        initiatives.record_not_found(site, "/books/OL1M", "lccn", user)
    assert site.store["contribute-notfound-OL1M-lccn"]["people"] == ["/people/a", "/people/b"]


def test_most_shelved_keeps_isbn_editions_two_per_work_and_tops_up_from_search(monkeypatch):
    rows = [
        {"edition_id": 1, "work_id": 10, "readers": 900},
        {"edition_id": 2, "work_id": 10, "readers": 800},
        {"edition_id": 3, "work_id": 10, "readers": 700},  # a third edition of work 10
        {"edition_id": 4, "work_id": 20, "readers": 600},  # no ISBN
        {"edition_id": 5, "work_id": 30, "readers": 500},  # merged away
    ]
    site = FakeSite(
        editions=[
            FakeEdition("/books/OL1M", isbn_13=["1"]),
            FakeEdition("/books/OL2M", isbn_10=["2"]),
            FakeEdition("/books/OL3M", isbn_13=["3"]),
            FakeEdition("/books/OL4M"),
            FakeEdition("/books/OL5M", type_key="/type/redirect", isbn_13=["5"]),
        ]
    )
    monkeypatch.setattr(initiatives.Bookshelves, "most_logged_editions_sync", lambda limit: rows)
    monkeypatch.setattr(initiatives, "pick_most_read", lambda size, site=None: [["/books/OL1M", 9], ["/books/OL9M", 8], ["/books/OL8M", 7]])

    assert initiatives.pick_most_shelved(3, site) == [["/books/OL1M", 900], ["/books/OL2M", 800], ["/books/OL9M", 8]]
    assert initiatives.pick_most_shelved(2, site) == [["/books/OL1M", 900], ["/books/OL2M", 800]]


def test_untagged_works_are_picked_one_edition_each_and_only_while_a_tag_is_missing(monkeypatch):
    tagged, bare, nonfiction = WORK, FakeWork("/works/OL2W"), FakeWork("/works/OL3W", literary_forms=[NONFICTION])
    rows = [
        {"edition_id": 1, "work_id": 1, "readers": 900},  # work fully tagged
        {"edition_id": 2, "work_id": 2, "readers": 800},
        {"edition_id": 3, "work_id": 2, "readers": 700},  # a second edition of the same work
        {"edition_id": 4, "work_id": 3, "readers": 600},  # nonfiction, so no genre to pick, but the form is filled too
        {"edition_id": 5, "work_id": 5, "readers": 500},  # an orphan: nowhere to put the answer
    ]
    site = FakeSite(
        editions=[
            FakeEdition("/books/OL1M", isbn_13=["1"], works=[tagged]),
            FakeEdition("/books/OL2M", isbn_13=["2"], works=[bare]),
            FakeEdition("/books/OL3M", isbn_13=["3"], works=[bare]),
            FakeEdition("/books/OL4M", isbn_13=["4"], works=[nonfiction]),
            FakeEdition("/books/OL5M", isbn_13=["5"]),
        ],
        works=(tagged, bare, nonfiction),
    )
    monkeypatch.setattr(initiatives.Bookshelves, "most_logged_editions_sync", lambda limit: rows)
    monkeypatch.setattr(initiatives, "pick_most_read", lambda size, site=None: [["/books/OL3M", 1], ["/books/OL6M", 1]])

    assert initiatives.pick_untagged_works(3, site) == [["/books/OL2M", 800]]


def test_the_pool_s_thread_builds_on_a_fresh_site_that_is_also_its_request_site(monkeypatch):
    seen = {}
    fresh, outer = object(), object()
    monkeypatch.setattr(initiatives, "create_site", lambda: fresh)
    monkeypatch.setattr(initiatives, "build_gaps", lambda initiative, site: seen.update(site=site, request=initiatives.request_site.get()) or ["gaps"])
    # Other tests can leave the ContextVar set, so pin a known outer value and check it comes back.
    token = initiatives.request_site.set(outer)
    try:
        assert initiatives.build_gaps_in_thread(initiatives.TAGS) == ["gaps"]
        assert seen == {"site": fresh, "request": fresh}
        assert initiatives.request_site.get() is outer
    finally:
        initiatives.request_site.reset(token)


NOW = datetime(2026, 12, 10, tzinfo=UTC)


def definition(slug="winter-covers", **more):
    return {"slug": slug, "title": "Winter Covers", "description": "Covers.", "fields": ["covers"], "starts_at": "2026-11-02T00:00:00+00:00"} | more


@pytest.mark.parametrize(
    ("starts_at", "ends_at", "expected"),
    [
        (None, None, "draft"),
        (NOW + timedelta(days=1), None, "scheduled"),
        (NOW, None, "live"),
        (NOW - timedelta(days=5), NOW + timedelta(days=1), "live"),
        (NOW - timedelta(days=5), NOW, "ended"),
    ],
)
def test_status_comes_from_the_dates(starts_at, ends_at, expected):
    initiative = initiatives.Initiative("test", 3, None, FOUR, starts_at=starts_at, ends_at=ends_at)
    assert initiative.status(NOW) == expected


def test_a_built_in_initiative_the_store_does_not_mention_is_the_one_defined_in_code():
    assert initiatives.every([]) == list(initiatives.BUILTIN)
    assert all(a is b for a, b in zip(initiatives.every([]), initiatives.BUILTIN))


def test_a_store_doc_adds_an_initiative_with_its_own_name():
    added = initiatives.every([definition(size=40, ends_at="2027-01-01")])[-1]
    assert (added.slug, added.size, added.fields, added.pick) == ("winter-covers", 40, ("covers",), None)
    assert (added.starts_at, added.ends_at) == (datetime(2026, 11, 2, tzinfo=UTC), datetime(2027, 1, 1, tzinfo=UTC))
    assert initiatives.describe(added) == {"title": "Winter Covers", "description": "Covers."}


def test_a_store_doc_overrides_only_the_keys_it_names_on_a_built_in_one():
    tags = initiatives.every([{"slug": initiatives.TAGS.slug, "hidden": True}])[1]
    assert tags == replace(initiatives.TAGS, hidden=True)
    assert tags.pick is initiatives.TAGS.pick


@pytest.mark.parametrize(
    "doc",
    [
        definition(slug=""),
        definition(title=""),
        definition(fields=["not-a-field"]),
        {"title": "No slug", "fields": ["covers"]},
    ],
)
def test_a_definition_that_cannot_be_an_initiative_is_skipped(doc):
    assert initiatives.every([doc]) == list(initiatives.BUILTIN)


def test_a_bad_override_leaves_the_built_in_one_as_it_was():
    assert initiatives.every([{"slug": initiatives.TAGS.slug, "fields": []}])[1] is initiatives.TAGS


def test_a_time_that_does_not_parse_makes_a_draft_and_a_bare_date_is_utc():
    assert initiatives.every([definition(starts_at="soon")])[-1].status() == "draft"
    assert initiatives.parse_time("2026-12-01") == datetime(2026, 12, 1, tzinfo=UTC)
    assert initiatives.parse_time("2026-12-01T02:00:00+02:00") == datetime(2026, 12, 1, tzinfo=UTC)


@pytest.fixture
def stored(monkeypatch):
    return lambda *docs: monkeypatch.setattr(initiatives, "cached_definitions", lambda: list(docs))


def slugs(found):
    return [i.slug for i in found]


def test_drafts_and_scheduled_initiatives_are_nowhere_public(stored):
    stored(definition("draft", starts_at=None), definition("later", starts_at="2999-01-01"))
    assert slugs(initiatives.every()) == [initiatives.MOST_READ.slug, initiatives.TAGS.slug, "later", "draft"]
    assert slugs(initiatives.started()) == slugs(initiatives.BUILTIN)
    assert initiatives.get("later") is None
    assert initiatives.get("later", hidden=True) is None


def test_a_hidden_initiative_is_off_the_lists_but_still_counted_and_still_takes_a_save(stored):
    stored(definition(hidden=True))
    assert "winter-covers" not in slugs(initiatives.listed())
    assert "winter-covers" in slugs(initiatives.started())
    assert initiatives.get("winter-covers") is None
    assert initiatives.get("winter-covers", hidden=True).slug == "winter-covers"


def test_an_ended_initiative_stays_listed_but_is_not_running(stored):
    stored(definition(ends_at="2026-11-03"))
    assert "winter-covers" in slugs(initiatives.listed())
    assert "winter-covers" not in slugs(initiatives.running())


def test_the_headline_is_the_featured_running_initiative(stored):
    stored(definition(featured=True), {"slug": initiatives.MOST_READ.slug, "featured": False})
    assert initiatives.headline().slug == "winter-covers"
    stored(definition(featured=True, ends_at="2026-11-03"))
    assert initiatives.headline() is initiatives.MOST_READ
    stored({"slug": initiatives.MOST_READ.slug, "hidden": True})
    assert initiatives.headline() is initiatives.TAGS


def test_an_initiative_with_no_picker_has_no_books_until_its_list_is_frozen():
    site = FakeSite()
    added = initiatives.every([definition()])[-1]
    assert initiatives.load_or_freeze(added, site) == []
    site.store[added.store_key] = {"editions": [["/books/OL1M", 5]]}
    assert initiatives.load_or_freeze(added, site) == [["/books/OL1M", 5]]


def test_an_ended_initiative_hands_out_no_tasks(monkeypatch):
    monkeypatch.setattr(initiatives, "get_gaps", lambda initiative: [["/books/OL1M", 5, ["covers"], []]])
    ended = initiatives.Initiative("test", 1, None, ("covers",), starts_at=datetime.now(UTC) - timedelta(days=9), ends_at=datetime.now(UTC) - timedelta(days=1))
    assert list(supply.candidates(ended, ("covers",))) == []
