from types import SimpleNamespace

import web

from openlibrary.contribute import book_page, initiatives, save

EDITION_KEY = "/books/OL1M"
ME = "/people/me"


class FakeEdition(dict):
    def __init__(self, key=EDITION_KEY, **fields):
        super().__init__(**fields)
        self.key = key
        self.type = web.storage(key="/type/edition")

    def dict(self):
        return dict(self) | {"key": self.key}


class FakeStore:
    """The store's one query the book page makes: every doc of a type whose ``name`` field is ``value``."""

    def __init__(self, docs=()):
        self.docs = list(docs)
        self.queries = 0

    def values(self, type=None, name=None, value=None):
        self.queries += 1
        return [doc for doc in self.docs if doc.get("type") == type and doc.get(name) == value]


class FakeSite:
    def __init__(self, docs=()):
        self.store = FakeStore(docs)
        self.saved = []

    def save(self, doc, comment=None, action=None, data=None):
        self.saved.append(web.storage(doc=doc, comment=comment, action=action, data=data))


def not_found(fld, people, edition=EDITION_KEY):
    return {"type": initiatives.NOT_FOUND_TYPE, "edition": edition, "field": fld, "people": people}


def test_a_page_offers_its_empty_fields_in_the_order_it_shows_them():
    edition = FakeEdition(publishers=["P"], number_of_pages=None, languages=[])
    assert book_page.open_fields(edition, FakeSite(), ME) == ["publish_date", "languages", "number_of_pages"]


def test_a_complete_edition_costs_no_store_query():
    site = FakeSite()
    edition = FakeEdition(publish_date="2001", publishers=["P"], languages=["eng"], number_of_pages=300)
    assert book_page.open_fields(edition, site, ME) == []
    assert site.store.queries == 0


def test_an_audiobook_is_not_asked_for_a_page_count():
    edition = FakeEdition(publish_date="2001", publishers=["P"], languages=["eng"], physical_format="Audio CD")
    assert book_page.open_fields(edition, FakeSite(), ME) == []


def test_a_field_enough_people_could_not_find_is_no_longer_asked():
    enough = [f"/people/p{n}" for n in range(initiatives.NOT_FOUND_PEOPLE["publishers"])]
    site = FakeSite([not_found("publishers", enough), not_found("languages", enough[:1])])
    assert book_page.open_fields(FakeEdition(publish_date="2001", number_of_pages=300), site, ME) == ["languages"]


def test_a_reader_is_not_asked_again_for_what_they_could_not_find():
    site = FakeSite([not_found("publishers", [ME])])
    edition = FakeEdition(publish_date="2001", number_of_pages=300, languages=["eng"])
    assert book_page.open_fields(edition, site, ME) == []
    assert book_page.open_fields(edition, site, "/people/someone-else") == ["publishers"]


def test_marks_on_another_edition_do_not_count():
    site = FakeSite([not_found("publishers", [ME], edition="/books/OL2M")])
    assert initiatives.not_found_on(site, EDITION_KEY, ME) == set()


def test_a_book_page_save_is_a_tasks_save_that_names_its_door(monkeypatch):
    site = FakeSite()
    monkeypatch.setattr(save, "site", SimpleNamespace(get=lambda: site))
    save.save_answer(FakeEdition(), "publishers", " Penguin ", "Publisher", door=book_page.DOOR)
    (change,) = site.saved
    assert change.doc["publishers"] == ["Penguin"]
    assert change.action == save.ACTION
    assert change.data == {"source": save.SOURCE, "field": "publishers", "door": "book-page"}
    assert change.comment == "Filled in Publisher from the book page"


def test_a_tasks_page_save_names_no_door(monkeypatch):
    site = FakeSite()
    monkeypatch.setattr(save, "site", SimpleNamespace(get=lambda: site))
    save.save_answer(FakeEdition(), "publishers", "Penguin", "Publisher")
    assert site.saved[0].data == {"source": save.SOURCE, "field": "publishers"}
    assert site.saved[0].comment == "Filled in Publisher from Open Library Tasks"


def test_a_save_is_credited_to_the_running_project_that_lists_the_book(monkeypatch):
    lead = initiatives.Initiative("lead", 3, None, ("publishers",))
    other = initiatives.Initiative("other", 3, None, ("publishers", "languages"))
    gaps = {"lead": [["/books/OL9M", 1, [], [], None]], "other": [[EDITION_KEY, 1, [], [], None]]}
    monkeypatch.setattr(initiatives, "headline", lambda: lead)
    monkeypatch.setattr(initiatives, "running", lambda: [other, lead])
    monkeypatch.setattr(initiatives, "get_gaps", lambda initiative: gaps[initiative.slug])
    assert initiatives.listing(EDITION_KEY, "publishers") is other
    assert initiatives.listing("/books/OL9M", "publishers") is lead
    assert initiatives.listing("/books/OL9M", "languages") is None
    assert initiatives.listing("/books/OL404M", "publishers") is None
