import web

from openlibrary.contribute import initiatives


class FakeStore(dict):
    def values(self, type=None, limit=100):
        return [doc for doc in dict.values(self) if doc.get("type") == type][:limit]


class FakeEdition(dict):
    def __init__(self, key, type_key="/type/edition", **fields):
        super().__init__(**fields)
        self.key = key
        self.type = web.storage(key=type_key)


class FakeSite:
    def __init__(self, editions=(), store=None):
        self.editions = {e.key: e for e in editions}
        self.store = FakeStore(store or {})

    def get_many(self, keys):
        return [self.editions[k] for k in keys if k in self.editions]


COMPLETE = {"covers": [1], "lccn": ["1"], "oclc_numbers": ["1"], "languages": ["eng"], "number_of_pages": 300, "publishers": ["P"]}


def make_initiative(picks, calls=None):
    def pick(size, site):
        if calls is not None:
            calls.append(size)
        return picks[:size]

    return initiatives.Initiative("test", 3, pick)


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
    assert initiatives.progress(gaps) == {"done": 1, "total": 2, "open": 1, "not_found": 1}


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
