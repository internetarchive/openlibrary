"""Tests for the home page's signed-in section (HomeMember partial)."""

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import web


def _home_member():
    # Imported lazily: importing the plugin at collection time hits a circular import.
    from openlibrary.plugins.openlibrary import home_member  # noqa: PLC0415

    return home_member


@pytest.fixture(autouse=True)
def no_search():
    """Search can't say which editions a reader could read, so the work's own copy is checked. Tests of the language rule say otherwise."""
    real = _home_member().readable_editions
    with patch("openlibrary.plugins.openlibrary.home_member.readable_editions", return_value=None) as readable:
        readable.real = real
        yield readable


def _book(title: str, **extra) -> dict:
    return {"title": title, "author": "", "url": f"/works/{title}", "cover_url": "", "thumb_url": ""} | extra


def _loan(title: str, days_left: int) -> dict:
    return _book(
        title, work_key=f"/works/{title}", ocaid=f"ia_{title}", can_read_here=True, days_left=days_left, due=f"due in {days_left}", urgent=days_left <= 2
    )


def _hold(title: str, *, ready: bool) -> dict:
    return _book(title, ready=ready, borrow_url=f"/books/{title}/borrow", note=f"note for {title}")


def _past(title: str, status: str | None) -> dict:
    return _book(
        title, work_key=f"/works/{title}", borrowed=f"borrowed {title}", availability={"status": status} if status else {}, borrow_url=f"/books/{title}/borrow"
    )


def test_logged_out_renders_nothing(fastapi_client):
    response = fastapi_client.get("/partials/HomeMember.json")
    assert response.status_code == 200
    assert response.json() == {"partials": ""}


def test_loans_card_lists_loans_then_ready_holds(request_context_fixture):
    request_context_fixture(lang="en")
    cards = _home_member().build_loans(
        loans=[_loan("soon", 1), _loan("later", 9)],
        holds=[_hold("waiting", ready=False), _hold("ready", ready=True)],
    )
    # A hold still in line has nothing to do yet, and is left to the loans page.
    assert [(card["title"], card["kind"]) for card in cards] == [("soon", "loan"), ("later", "loan"), ("ready", "ready")]
    assert cards[0]["tone"] == "urgent"
    assert cards[0]["action"]["form"] == {"action": "/borrow/ia/ia_soon", "value": "read"}
    assert cards[2]["action"]["form"] == {"action": "/books/ready/borrow", "value": "borrow"}
    # A ready hold says how long it is kept.
    assert cards[2]["status"] == "note for ready"


def test_greeting_name_skips_usernames_and_long_names():
    name = _home_member().greeting_name
    assert name(SimpleNamespace(key="/people/mek", displayname="Mek K")) == "Mek K"
    assert name(SimpleNamespace(key="/people/mek", displayname="mek")) == ""
    assert name(SimpleNamespace(key="/people/mek", displayname=None)) == ""
    assert name(SimpleNamespace(key="/people/mek", displayname="x" * 31)) == ""


def test_shelves_lead_with_currently_reading_and_show_a_work_once(request_context_fixture):
    request_context_fixture(lang="en")
    shelves = {
        "currently-reading": [web.storage(key="/works/OL1W", title="reading", ia=["r00"]), web.storage(key="/works/OL9W")],
        "want-to-read": [web.storage(key="/works/OL2W", title="wanted", ia=["w00"]), web.storage(key="/works/OL1W", title="reading", ia=["r00"])],
    }
    asked = []

    def add_availability(items):
        for item in items:
            item["availability"] = {"status": "borrow_available"}

    class ReadLog:
        def get_works(self, key, limit, fq):
            asked.append((key, limit))
            return web.storage(docs=shelves[key])

    with patch("openlibrary.core.lending.add_availability_async", side_effect=add_availability):
        books, known = _home_member().shelves_available(ReadLog(), _home_member().AvailabilityBudget())

    assert known
    assert asked == [("currently-reading", _home_member().READING_CHECKED), ("want-to-read", _home_member().WANT_CHECKED)]
    # The work not in search (no title) is dropped; the one on both shelves is shown once, as Currently Reading.
    assert [(doc["title"], doc["shelf"]) for doc in books] == [("reading", "reading"), ("wanted", "want")]
    assert [_home_member().want_brief(doc, checked=True)["shelf"] for doc in books] == ["reading", "want"]


def test_shelves_available_keeps_only_copies_free_now(request_context_fixture):
    request_context_fixture(lang="en")
    docs = [
        web.storage(key="/works/OL1W", title="free", ia=["free00"]),
        web.storage(key="/works/OL2W", title="out", ia=["out00"]),
        web.storage(key="/works/OL3W", title="open", ia=["open00"]),
        web.storage(key="/works/OL4W", title="unknown", ia=["unknown00"]),
    ]
    statuses = {"free": "borrow_available", "out": "borrow_unavailable", "open": "open", "unknown": "error"}

    def add_availability(items):
        for item in items:
            item["availability"] = {"status": statuses[item["title"]]}

    class ReadLog:
        def get_works(self, key, limit, fq):
            return web.storage(docs=docs if key == "want-to-read" else [])

    with patch("openlibrary.core.lending.add_availability_async", side_effect=add_availability):
        free, known = _home_member().shelves_available(ReadLog(), _home_member().AvailabilityBudget())

    assert known
    assert [doc["title"] for doc in free] == ["free", "open"]


def test_print_disabled_readers_can_open_print_disabled_copies(request_context_fixture):
    """A copy in the print-disabled collection counts as free for a print-disabled reader, lent out or not, and for them only."""
    docs = [
        web.storage(key="/works/OL1W", title="free", ia=["free00"]),
        web.storage(key="/works/OL2W", title="pd only", ia=["pd00"]),
        web.storage(key="/works/OL3W", title="pd, all lent out", ia=["lent00"]),
        web.storage(key="/works/OL4W", title="lent out", ia=["out00"]),
    ]
    availability = {
        "free": {"status": "borrow_available"},
        "pd only": {"status": "private", "is_printdisabled": True},
        "pd, all lent out": {"status": "borrow_unavailable", "is_printdisabled": True, "is_lendable": True},
        "lent out": {"status": "borrow_unavailable", "is_lendable": True},
    }

    def add_availability(items):
        for item in items:
            item["availability"] = availability[item["title"]]

    class ReadLog:
        def get_works(self, key, limit, fq=None):
            return web.storage(docs=docs)

    def shelves():
        with patch("openlibrary.core.lending.add_availability_async", side_effect=add_availability):
            books, _known = _home_member().shelves_available(ReadLog(), _home_member().AvailabilityBudget())
        return [doc["title"] for doc in books]

    request_context_fixture(lang="en", print_disabled=True)
    assert shelves() == ["free", "pd only", "pd, all lent out"]
    request_context_fixture(lang="en", print_disabled=False)
    assert shelves() == ["free"]


def test_shelves_available_shows_the_shelf_when_availability_cannot_be_read(request_context_fixture):
    request_context_fixture(lang="en")
    docs = [web.storage(key="/works/OL1W", title="one", ia=["one00"]), web.storage(key="/works/OL2W", title="two", ia=["two00"])]

    class ReadLog:
        def get_works(self, key, limit, fq):
            return web.storage(docs=docs)

    def errors(items):
        for item in items:
            item["availability"] = {"status": "error"}

    # The service answers with nothing (`success: false`), or with an error for every book (a timeout).
    for add_availability in (lambda items: None, errors):
        with patch("openlibrary.core.lending.add_availability_async", side_effect=add_availability):
            want, known = _home_member().shelves_available(ReadLog(), _home_member().AvailabilityBudget())
        assert not known
        assert [doc["title"] for doc in want] == ["one", "two"]


def test_shelves_available_prefers_the_shelved_edition_when_it_is_free(request_context_fixture):
    request_context_fixture(lang="en")
    docs = [
        # The shelved edition is free: it is the copy offered, even with the work's own copy free too.
        web.storage(key="/works/OL1W", title="mine", ia=["work1"], cover_i=1, editions=[{"key": "/books/OL1M", "ia": ["mine1"], "cover_i": 11}]),
        # The shelved edition is out: the work's copy stands in.
        web.storage(key="/works/OL2W", title="other", ia=["work2"], cover_i=2, editions={"docs": [{"key": "/books/OL2M", "ia": ["mine2"], "cover_i": 22}]}),
        # Neither is free.
        web.storage(key="/works/OL3W", title="none", ia=["work3"], editions=[{"key": "/books/OL3M", "ia": ["mine3"]}]),
    ]
    free = {"work1", "mine1", "work2"}
    calls = []

    def add_availability(items):
        calls.append(len(items))
        for item in items:
            item["availability"] = {"status": "borrow_available" if item["ia"][0] in free else "borrow_unavailable", "identifier": item["ia"][0]}

    class ReadLog:
        def get_works(self, key, limit, fq):
            return web.storage(docs=docs)

    with patch("openlibrary.core.lending.add_availability_async", side_effect=add_availability):
        want, known = _home_member().shelves_available(ReadLog(), _home_member().AvailabilityBudget())

    assert known
    assert calls == [6]  # works and shelved editions in one request
    assert [_home_member().want_brief(doc, checked=True)["url"] for doc in want] == ["/works/OL1W?edition=ia:mine1", "/works/OL2W?edition=ia:work2"]
    # The cover follows the copy: the shelved edition's when that is the one offered, else the work's.
    assert [_home_member().brief_from_doc(doc)["cover_url"].rsplit("/", 1)[-1] for doc in want] == ["11-M.jpg", "2-M.jpg"]


def test_shelves_available_offers_only_copies_the_reader_could_read(request_context_fixture, no_search):
    request_context_fixture(lang="en")
    docs = [
        # The work's own lending copy is a translation, and free. An English edition is free too: that one is offered.
        web.storage(key="/works/OL1W", title="english free", ia=["turkish1"]),
        # The first English edition is out, the next is free.
        web.storage(key="/works/OL2W", title="second english", ia=["turkish2"]),
        # Every English edition is out: left off, though the translation is free.
        web.storage(key="/works/OL3W", title="english out", ia=["turkish3"]),
        # Only translations have an ebook: left off.
        web.storage(key="/works/OL4W", title="translations only", ia=["turkish4"]),
        # A translation the reader shelved themselves is their choice, and is offered.
        web.storage(key="/works/OL5W", title="shelved translation", ia=["turkish5"], editions=[{"key": "/books/OL5M", "ia": ["shelved5"], "language": ["tur"]}]),
    ]
    no_search.return_value = {
        "/works/OL1W": [{"key": "/books/OL11M", "ia": ["english1"]}],
        "/works/OL2W": [{"key": "/books/OL21M", "ia": ["out2"]}, {"key": "/books/OL22M", "ia": ["english2"]}],
        "/works/OL3W": [{"key": "/books/OL31M", "ia": ["out3"]}],
        "/works/OL4W": [],
        "/works/OL5W": [],
    }
    checked = []

    def add_availability(items):
        for item in items:
            checked.append(item["ia"][0])
            item["availability"] = {"status": "borrow_unavailable" if item["ia"][0].startswith("out") else "borrow_available"}

    class ReadLog:
        def get_works(self, key, limit, fq):
            return web.storage(docs=docs)

    with patch("openlibrary.core.lending.add_availability_async", side_effect=add_availability):
        want, known = _home_member().shelves_available(ReadLog(), _home_member().AvailabilityBudget())

    assert known
    # No translation the reader didn't choose is even asked about.
    assert sorted(checked) == ["english1", "english2", "out2", "out3", "shelved5"]
    assert [_home_member().want_brief(doc, checked=True)["url"] for doc in want] == [
        "/works/OL1W?edition=ia:english1",
        "/works/OL2W?edition=ia:english2",
        "/works/OL5W?edition=ia:shelved5",
    ]


def test_readable_editions_asks_for_the_readers_language(request_context_fixture, no_search):
    request_context_fixture(lang="fr")
    asked = {}

    class Solr:
        async def raw_request(self, path, payload, _timeout=None):
            from urllib.parse import parse_qs  # noqa: PLC0415

            asked.update(parse_qs(payload))
            return SimpleNamespace(json=lambda: {"response": {"docs": [{"key": "/works/OL1W", "copies": {"docs": copies}}, {"key": "/works/OL2W"}]}})

    real = no_search.real
    docs = [web.storage(key="/works/OL1W"), web.storage(key="/works/OL2W")]
    french, unrecorded = {"key": "/books/OL1M", "ia": ["fr"], "language": ["fre"]}, {"key": "/books/OL2M", "ia": ["none"]}
    # Search sends every ebook edition, the reader's language first. A translation and an edition with no scan are left out.
    copies = [french, {"key": "/books/OL3M", "ia": ["tr"], "language": ["tur"]}, unrecorded, {"key": "/books/OL4M", "language": ["fre"]}]

    class Down:
        async def raw_request(self, path, payload, _timeout=None):
            raise OSError

    class OutOfTime:
        async def raw_request(self, path, payload, _timeout=None):
            return SimpleNamespace(json=lambda: {"responseHeader": {"partialResults": True}, "response": {"docs": []}})

    with patch("openlibrary.plugins.upstream.utils.convert_iso_to_marc", return_value="fre"):
        with patch("openlibrary.plugins.worksearch.search.get_solr", return_value=Solr()):
            assert real(docs) == {"/works/OL1W": [french, unrecorded], "/works/OL2W": []}
        assert asked["q"] == ["{!terms f=key}/works/OL1W,/works/OL2W"]
        assert "language:fre^40" in asked["copies.q"][0]
        # Search that is down, or that ran out of time before seeing every edition, has no answer to use.
        for solr in (Down(), OutOfTime()):
            with patch("openlibrary.plugins.worksearch.search.get_solr", return_value=solr):
                assert real(docs) is None


def test_want_brief_links_to_the_copy_that_was_checked(request_context_fixture):
    request_context_fixture(lang="en")
    doc = web.storage(key="/works/OL1W", title="free", ia=["free00"], availability={"status": "open", "identifier": "free00"})

    assert _home_member().want_brief(doc, checked=True)["url"] == "/works/OL1W?edition=ia:free00"
    # Not checked for a free copy: the work page chooses.
    assert _home_member().want_brief(doc, checked=False)["url"] == "/works/OL1W"


def test_availability_gets_one_budget_for_the_section(request_context_fixture):
    request_context_fixture(lang="en")
    import asyncio  # noqa: PLC0415

    calls = []

    async def slow(items):
        calls.append(items)
        await asyncio.sleep(5)

    docs = [web.storage(key="/works/OL1W", title="one", ia=["one00"])]
    budget = _home_member().AvailabilityBudget(0.05)
    with patch("openlibrary.core.lending.add_availability_async", side_effect=slow):
        assert not budget.add(docs)
        # The time is spent: the next check isn't made.
        assert not budget.add(docs)
        # Books with nothing to check cost nothing.
        assert budget.add([web.storage(key="/works/OL2W", title="no ebook")])
    assert len(calls) == 1


def test_generate_keeps_the_request_context(request_context_fixture):
    """Replacing it from the bare web.ctx marks the request a bot, and availability then skips the real check."""
    from openlibrary.plugins.openlibrary import partials  # noqa: PLC0415
    from openlibrary.utils.request_context import req_context  # noqa: PLC0415

    request_context_fixture(lang="en", is_bot=False)
    before = req_context.get()
    with (
        patch.object(partials.delegate, "fakeload"),
        patch.object(partials.home_member, "get_cached_html", return_value=None),
        patch.object(partials, "get_user_object", return_value=None),
    ):
        assert partials.HomeMemberPartial.generate("someone") == {"partials": ""}
    assert req_context.get() is before


def test_cached_section_is_served_until_the_shelves_change(request_context_fixture):
    request_context_fixture(lang="en")
    home_member = _home_member()
    store: dict = {}

    class Memcache:
        def get(self, key):
            return store.get(key)

        def set(self, key, value, expires=0):
            store[key] = value

        def delete(self, key):
            store.pop(key, None)

    version = ["v1"]
    with (
        patch.object(home_member.cache, "get_memcache", return_value=Memcache()),
        patch.object(home_member.Bookshelves, "reading_log_version", side_effect=lambda username: version[0]),
    ):

        def get(part):
            return home_member.get_cached_html("reader", part, home_member.cache_variant("reader"))

        def put(part, html):
            home_member.cache_html("reader", part, html, home_member.cache_variant("reader"))

        assert get("loans") is None
        put("loans", "<section>")
        assert get("loans") == "<section>"
        # The halves are kept apart.
        assert get("shelves") is None
        put("shelves", "<wall>")
        assert get("loans") == "<section>"
        version[0] = "v2"  # a book was shelved
        assert get("loans") is None
        assert get("shelves") is None
        put("loans", "<new>")
        put("shelves", "<new wall>")
        home_member.invalidate_cache("reader")  # a borrow or return
        assert get("loans") is None
        assert get("shelves") is None
        # A shelf change while a half is being built: it is stored under the version it was built from.
        variant = home_member.cache_variant("reader")
        version[0] = "v3"
        home_member.cache_html("reader", "loans", "<built from v2>", variant)
        assert get("loans") is None


def test_due_dates_count_calendar_days(request_context_fixture):
    """A loan due tomorrow night is due tomorrow, though it's more than a day away; one due just after midnight is due tomorrow too."""
    from datetime import datetime  # noqa: PLC0415

    request_context_fixture(lang="en")
    home_member = _home_member()

    class Now(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 18, 23, 0, tzinfo=tz)

    loans = [{"book": "/books/OL1M", "ocaid": "a", "expiry": "2026-11-19T00:30:00"}, {"book": "/books/OL2M", "ocaid": "b", "expiry": "2026-11-20T22:00:00"}]
    book = SimpleNamespace(title="Book", key="/books/OL1M", works=[], url=lambda: "/books/OL1M", get_authors=list, get_cover_url=lambda size: "")
    with (
        patch.object(home_member, "datetime", Now),
        patch.object(home_member.lending, "get_cached_loans_of_user", return_value=loans),
        patch.object(home_member, "site", SimpleNamespace(get=lambda: SimpleNamespace(get=lambda key: book))),
    ):
        assert [loan["days_left"] for loan in home_member.get_loans("/people/reader")] == [1, 2]


def test_the_card_is_labelled_by_what_it_holds(request_context_fixture):
    request_context_fixture(lang="en")
    from openlibrary.core.jinja import get_jinja_env, render_jinja_template  # noqa: PLC0415

    def label(**books):
        cards = _home_member().build_loans(**{"loans": [], "holds": []} | books)
        with patch.dict(get_jinja_env().globals, {"icon": lambda *args, **kwargs: ""}):
            html = render_jinja_template("home/member.html.jinja", member={"name": "", "complete": True, "part": "loans", "loans": cards})
        return html.split('class="home-now__label">', 1)[1].split("</h3>", 1)[0].strip()

    assert label(loans=[_loan("borrowed", 5)]) == "Checked Out"
    assert label(holds=[_hold("ready", ready=True)]) == "Ready to Borrow"
    assert label(loans=[_loan("borrowed", 5)], holds=[_hold("ready", ready=True)]) == "Loans and Holds"
    assert label(past=[_past("returned", "borrow_available")]) == "Recently Borrowed"
    assert label(loans=[_loan("borrowed", 5)], past=[_past("returned", "borrow_available")]) == "Your Loans"


def test_past_loans_follow_current_ones_once_each_with_what_can_be_done_now(request_context_fixture):
    request_context_fixture(lang="en")
    cards = _home_member().build_loans(
        loans=[_loan("out", 3)],
        holds=[_hold("waiting", ready=False) | {"work_key": "/works/waiting"}],
        past=[
            _past("out", "borrow_available"),
            _past("waiting", "borrow_unavailable"),
            _past("free", "borrow_available"),
            _past("lent", "borrow_unavailable"),
            _past("open", "open"),
            _past("private", "private"),
            _past("free", "borrow_available"),
        ],
    )
    # A book the reader has out or is waiting for is shown once, as that.
    assert [(card["title"], card["kind"]) for card in cards] == [("out", "loan"), ("free", "past"), ("lent", "past"), ("open", "past"), ("private", "past")]
    past = {card["title"]: card for card in cards[1:]}
    assert past["free"]["status"] == "borrowed free"
    assert (past["free"]["action"]["label"], past["free"]["action"]["form"]) == ("Borrow again", {"action": "/books/free/borrow", "value": "borrow"})
    assert past["lent"]["action"]["form"] == {"action": "/books/lent/borrow", "value": "join-waitinglist"}
    assert (past["open"]["action"]["label"], past["open"]["action"]["form"]) == ("Read", None)
    assert (past["private"]["action"]["label"], past["private"]["action"]["form"]) == ("View book", None)


def test_a_print_disabled_reader_can_borrow_a_past_loan_that_is_lent_out(request_context_fixture):
    request_context_fixture(lang="en", print_disabled=True)
    past = _past("lent", "borrow_unavailable") | {"availability": {"status": "borrow_unavailable", "is_printdisabled": True}}
    [card] = _home_member().build_loans(loans=[], holds=[], past=[past])
    assert card["action"]["form"] == {"action": "/books/lent/borrow", "value": "borrow"}


def _history(*identifiers: str) -> dict:
    return {"history": {"items": [{"identifier": ocaid, "updatedate": "2026-11-20 14:03:11"} for ocaid in identifiers]}}


def test_past_loans_come_from_the_readers_loan_history(request_context_fixture):
    request_context_fixture(lang="en")
    home_member = _home_member()
    edition = web.storage(
        title="Returned",
        key="/books/OL1M",
        works=[web.storage(key="/works/OL1W")],
        availability={"status": "borrow_available"},
        get_authors=list,
        get_cover_url=lambda size: "",
        url=lambda suffix="": f"/books/OL1M/Returned{suffix}",
    )
    loan_api = AsyncMock(return_value=SimpleNamespace(json=lambda: _history("ia_only_item", "returned_item")))
    with (
        patch.object(home_member, "parse_s3_cookie", return_value={"access": "a", "secret": "s"}),
        patch.object(home_member.lending, "s3_loan_api_async", loan_api),
        patch.object(home_member.lending, "get_availability_async", AsyncMock(return_value={})) as availability,
        # Books only on archive.org have no edition here and are left out.
        patch.object(home_member.lending, "editions_for_availability", return_value={"returned_item": edition}),
    ):
        [past] = home_member.get_past_loans("cookie")
    assert loan_api.call_args.kwargs["limit"] == home_member.PAST_LOANS_CHECKED
    availability.assert_awaited_once_with("identifier", ["ia_only_item", "returned_item"])
    assert past["work_key"] == "/works/OL1W"
    assert past["borrow_url"] == "/books/OL1M/Returned/borrow"
    assert past["borrowed"].startswith("Borrowed ")
    assert home_member.borrowed_label("") == "Borrowed before"


def test_a_reader_without_ia_keys_has_no_past_loans(request_context_fixture):
    request_context_fixture(lang="en")
    home_member = _home_member()
    with patch.object(home_member.lending, "s3_loan_api_async") as loan_api:
        assert home_member.get_past_loans(None) == []
    loan_api.assert_not_called()


def test_a_slow_loan_history_is_given_up_on(request_context_fixture):
    request_context_fixture(lang="en")
    home_member = _home_member()

    async def slow(**kwargs):
        await asyncio.sleep(5)

    started = time.monotonic()
    with (
        patch.object(home_member, "HISTORY_BUDGET_SECS", 0.05),
        patch.object(home_member, "parse_s3_cookie", return_value={"access": "a", "secret": "s"}),
        patch.object(home_member.lending, "s3_loan_api_async", slow),
    ):
        assert home_member.get_past_loans("cookie") == []
    assert time.monotonic() - started < 1


def test_a_half_missing_only_its_loan_history_is_still_kept(request_context_fixture):
    request_context_fixture(lang="en")
    home_member = _home_member()
    user = SimpleNamespace(key="/people/mek", displayname="Mek K")
    with (
        patch.object(home_member, "get_loans", return_value=[]),
        patch.object(home_member, "get_holds", return_value=[]),
        patch.object(home_member, "get_past_loans", side_effect=Exception("IA down")),
    ):
        member = home_member.build_part(user, "loans", "cookie")
    assert member["loans"] == []
    assert member["complete"]


def test_each_half_builds_only_its_own_books(request_context_fixture):
    request_context_fixture(lang="en")
    home_member = _home_member()
    user = SimpleNamespace(key="/people/mek", displayname="Mek K")
    with (
        patch("openlibrary.plugins.upstream.mybooks.ReadingLog"),
        patch.object(home_member, "get_loans", return_value=[_loan(str(n), n) for n in range(4)]) as loans,
        patch.object(home_member, "get_holds", return_value=[_hold("ready", ready=True)]),
        patch.object(home_member, "shelves_available", return_value=([{"key": "/works/OL1W", "title": "wanted", "shelf": "want"}], False)) as shelves,
        patch.object(home_member, "get_past_loans", return_value=[_past("returned", "borrow_available")]) as past,
    ):
        member = home_member.build_part(user, "loans", "cookie")
        # As many as the card holds, soonest due first. A full card doesn't ask for the loan history.
        assert [card["title"] for card in member["loans"]] == ["0", "1"]
        assert member["complete"]
        assert "shelves" not in member
        shelves.assert_not_called()
        past.assert_not_called()

        loans.return_value = [_loan("0", 0)]
        member = home_member.build_part(user, "loans", "cookie")
        assert [card["title"] for card in member["loans"]] == ["0", "ready"]
        past.assert_not_called()

        loans.return_value = []
        member = home_member.build_part(user, "loans", "cookie")
        assert [card["title"] for card in member["loans"]] == ["ready", "returned"]
        past.assert_called_once_with("cookie")

        member = home_member.build_part(user, "shelves")
        assert [book["title"] for book in member["shelves"]] == ["wanted"]
        assert "loans" not in member
        # Built without availability: shown, and not kept.
        assert not member["shelves_checked"]
        assert not member["complete"]
        assert shelves.call_count == 1


def test_a_half_renders_the_heading_and_itself_or_nothing(request_context_fixture):
    request_context_fixture(lang="en")
    from openlibrary.core.jinja import get_jinja_env, render_jinja_template  # noqa: PLC0415

    def render(member):
        # The icon macro needs the running site.
        with patch.dict(get_jinja_env().globals, {"icon": lambda *args, **kwargs: ""}):
            return render_jinja_template("home/member.html.jinja", member={"name": "Mek K", "complete": True} | member).strip()

    shelves = render({"part": "shelves", "shelves": [_book("wanted", shelf="want")], "shelves_checked": True})
    assert "Welcome back, Mek K" in shelves
    assert 'class="home-now__shelves"' in shelves
    assert "home-now__loans" not in shelves
    assert "Ready to Read Now" in shelves
    assert "/account/books/currently-reading" in shelves
    assert "/account/books/want-to-read" in shelves

    cards = _home_member().build_loans(loans=[_loan("borrowed", 5)], holds=[])
    loans = render({"part": "loans", "loans": cards})
    assert "Welcome back, Mek K" in loans
    assert 'class="home-now__loans"' in loans
    assert "home-now__shelves" not in loans
    assert "See All Loans" in loans

    assert render({"part": "shelves", "shelves": [], "shelves_checked": True}) == ""
    assert render({"part": "loans", "loans": []}) == ""


def test_a_ready_hold_shows_how_long_it_is_kept(request_context_fixture):
    request_context_fixture(lang="en")
    from openlibrary.core.jinja import get_jinja_env, render_jinja_template  # noqa: PLC0415

    home_member = _home_member()
    hold = _hold("ready", ready=True) | {"note": home_member.ready_label(2.2)}
    # Alone it takes the large layout, beside a loan a line; either way its countdown shows.
    for loans in ([], [_loan("borrowed", 5)]):
        cards = home_member.build_loans(loans=loans, holds=[hold])
        with patch.dict(get_jinja_env().globals, {"icon": lambda *args, **kwargs: ""}):
            html = render_jinja_template("home/member.html.jinja", member={"name": "", "complete": True, "part": "loans", "loans": cards})
        assert "Held for you for 2 more hours." in html


def test_labels_count_and_pluralise(request_context_fixture):
    request_context_fixture(lang="en")
    home_member = _home_member()
    assert [home_member.due_label(days) for days in (-1, 0, 1, 2)] == ["Due back today", "Due back today", "Due back tomorrow", "Due back in 2 days"]
    assert home_member.ready_label(0) == "Borrow it soon, or it goes to the next reader."
    assert home_member.ready_label(0.4) == "Held for you for 1 more hour."
    assert home_member.ready_label(30) == "Held for you for 1 more day."
    assert home_member.ready_label(60) == "Held for you for 2 more days."
    assert home_member.waiting_label(1, 4) == "You're next in line"
    assert home_member.waiting_label(3, 7) == "You're number 3 of 7 in line"
