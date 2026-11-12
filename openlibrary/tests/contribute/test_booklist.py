import web

from openlibrary.contribute import booklist


class Doc(dict):
    def __init__(self, key, type_key="/type/edition", **fields):
        super().__init__(**fields)
        self.key = key
        self.type = web.storage(key=type_key)


W1, W2 = Doc("/works/OL1W", "/type/work"), Doc("/works/OL2W", "/type/work")
EMPTY_WORK = Doc("/works/OL9W", "/type/work")
E1 = Doc("/books/OL1M", isbn_13=["9780140328721"], works=[W1])
E2 = Doc("/books/OL2M", works=[W1])
E3 = Doc("/books/OL3M", isbn_10=["0140328726"], works=[W2])
AUTHOR = Doc("/authors/OL1A", "/type/author")


class FakeSite:
    def __init__(self, *docs):
        self.docs = {d.key: d for d in docs}

    def get(self, key):
        return self.docs.get(key)

    def get_many(self, keys):
        return [self.docs[k] for k in keys if k in self.docs]

    def things(self, query):
        if "works" in query:
            return [d.key for d in self.docs.values() if d.type.key == "/type/edition" and any(w.key == query["works"] for w in d.get("works", []))]
        name = next(k for k in query if k.startswith("isbn_"))
        return [d.key for d in self.docs.values() if query[name] in d.get(name, [])]


SITE = FakeSite(W1, W2, EMPTY_WORK, E1, E2, E3)


def reasons(resolved):
    return {s["entry"]: s["reason"] for s in resolved.skipped}


def test_entries_split_on_lines_commas_and_spaces_and_an_isbn_keeps_its_hyphens():
    assert booklist.split_entries("OL1M, OL2M\n978-0-14-032872-1;  OL3W ") == ["OL1M", "OL2M", "978-0-14-032872-1", "OL3W"]


def test_an_edition_is_named_by_its_id_its_key_or_its_url():
    resolved = booklist.resolve(SITE, ["OL1M", "https://openlibrary.org/books/OL3M/A_Title"])
    assert resolved.picks == [["/books/OL1M", None], ["/books/OL3M", None]]
    assert resolved.skipped == []


def test_an_isbn_names_the_edition_that_carries_it_in_either_form():
    resolved = booklist.resolve(SITE, ["978-0-14-032872-1", "0140328726", "9999999999"])
    # The ISBN-10 is the same book as the ISBN-13 on OL1M, which is found first.
    assert resolved.picks == [["/books/OL1M", None]]
    assert reasons(resolved) == {"0140328726": "duplicate", "9999999999": "no_isbn"}


def test_a_work_is_added_as_its_edition_with_an_isbn():
    assert booklist.resolve(SITE, ["OL1W"]).picks == [["/books/OL1M", None]]
    assert reasons(booklist.resolve(SITE, ["OL9W"])) == {"OL9W": "no_edition"}


def test_what_cannot_be_used_is_skipped_with_its_reason():
    site = FakeSite(E1, AUTHOR)
    resolved = booklist.resolve(site, ["nonsense", "OL404M", "OL1M", "/books/OL1M"])
    assert resolved.picks == [["/books/OL1M", None]]
    assert reasons(resolved) == {"nonsense": "unknown", "OL404M": "missing", "/books/OL1M": "duplicate"}


def test_one_per_work_skips_a_second_edition_of_the_same_work():
    assert len(booklist.resolve(SITE, ["OL1M", "OL2M", "OL3M"]).picks) == 3
    resolved = booklist.resolve(SITE, ["OL1M", "OL2M", "OL3M"], one_per_work=True)
    assert resolved.picks == [["/books/OL1M", None], ["/books/OL3M", None]]
    assert reasons(resolved) == {"OL2M": "same_work"}


def test_the_list_stops_at_the_limit(monkeypatch):
    monkeypatch.setattr(booklist, "MAX_BOOKS", 1)
    assert reasons(booklist.resolve(SITE, ["OL1M", "OL3M"])) == {"OL3M": "over_limit"}


def test_a_list_gives_its_books_and_skips_its_other_seeds():
    lst = Doc("/people/mek/lists/OL5L", "/type/list")
    lst.get_seeds = lambda: [web.storage(key="/books/OL1M"), web.storage(key="/works/OL2W"), web.storage(key="subject:cats")]
    site = FakeSite(W1, W2, E1, E3, lst)
    resolved = booklist.resolve_list(site, "https://openlibrary.org/people/mek/lists/OL5L/My_List")
    assert resolved.picks == [["/books/OL1M", None], ["/books/OL3M", None]]
    assert reasons(resolved) == {"subject:cats": "unknown"}
    assert booklist.resolve_list(site, "/people/mek/lists/OL404L") is None
    assert booklist.resolve_list(site, "not a list") is None
