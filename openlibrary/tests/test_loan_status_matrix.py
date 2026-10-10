"""Golden matrix for openlibrary/macros/LoanStatus.html.

LoanStatus decides which button a book shows.  It takes a nine-value lending
state plus a handful of per-call-site flags and threads them through eleven
hand-written conditionals, every one of which independently re-derives the
answer to the same question: which surface am I on?

PR #13314 changed six of the seven places that ask that question and missed the
seventh, which had no ``$else`` -- so outside the book page a preview-only book
showed the sentence "Only a preview is available." and no way to open the
preview, until #13491 restored the button.  Nothing could have caught that:
every existing lending test asserts on the *string* ``get_lending_state()``
returns, and not one renders the macro.  The whole mapping from state to markup
is otherwise untested.

This module is that mapping, written down.  ``MATRIX`` names, for every
reachable case against each of the four real call sites, the primary call to
action, the auxiliary controls beside it, and any explanatory note -- as action
names, not markup.  What each action looks like in the DOM lives once per
action in ``ACTIONS``.  The tests render the macro and check the two agree.

Nothing here is generated: the table *is* the expectation, so changing what a
book offers means editing a row and saying why in the commit that does it.
"""

from dataclasses import dataclass, field
from typing import Any

import pytest
import web
from bs4 import BeautifulSoup, Tag

from infogami.utils import macro

OCAID = "matrixbook"
EDITION_KEY = "/books/OL1M"
WORK_KEY = "/works/OL1W"
REQUEST_PATH = "/works/OL1W"


# ---------------------------------------------------------------------------
# Surfaces -- the four real call sites, with the arguments they actually pass.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Surface:
    name: str
    call_site: str
    kwargs: dict[str, Any]


BOOK_PAGE = "book_page"
EDITIONS_TABLE = "editions_table"
SEARCH_ROW = "search_row"
CAROUSEL = "carousel"

SURFACES = {
    # databarWork passes allow_expensive_availability_check too; it is omitted
    # here because it triggers a network call and -- per the audit's F-1 -- can
    # no longer change which branch is taken anyway.
    BOOK_PAGE: Surface(BOOK_PAGE, "macros/databarWork.html:39", {"secondary_action": True, "check_loan_status": True}),
    EDITIONS_TABLE: Surface(EDITIONS_TABLE, "templates/books/edition-sort.html:93", {"is_book_page": True}),
    SEARCH_ROW: Surface(SEARCH_ROW, "macros/SearchResultsWork.html:253", {"work_key": WORK_KEY}),
    CAROUSEL: Surface(
        CAROUSEL,
        "templates/books/custom_carousel_card.html:87",
        {"work_key": WORK_KEY, "listen": False, "analytics_override": "BookCarousel|{action}Click|OL1W"},
    ),
}

# Shorthands for the surface column below.  LISTS is the pair that keeps the
# "more reading options" dropper; the carousel drops it by passing listen=False.
ANY = (BOOK_PAGE, EDITIONS_TABLE, SEARCH_ROW, CAROUSEL)
LISTS = (EDITIONS_TABLE, SEARCH_ROW)
OFF_BOOK_PAGE = (EDITIONS_TABLE, SEARCH_ROW, CAROUSEL)


# ---------------------------------------------------------------------------
# Cases -- one per reachable (lending state, sub-condition) pair.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Case:
    key: str
    state: str
    doc_fields: dict[str, Any] = field(default_factory=dict)
    waiting_loan: dict[str, Any] | None = None
    comment: str = ""

    def build_doc(self) -> web.storage:
        doc = web.storage(
            key=EDITION_KEY,
            title="Matrix Test Book",
            ocaid=OCAID,
            availability={},
            works=[{"key": WORK_KEY}],
        )
        doc.update(self.doc_fields)
        return doc


LENDABLE = {"is_lendable": True}

CASES = {
    case.key: case
    for case in (
        Case(
            "borrowed",
            "borrowed",
            {"loan": {"userid": "/people/reader", "expiry": "2026-09-01T00:00:00"}},
        ),
        # The partner branch reads an acquisition, never the surface.  DirectProvider
        # keeps anything at PRINTDISABLED or above, so "borrow" reaches a
        # read_button.html that has only open-access and sample branches.
        Case(
            "partner:open-access",
            "partner",
            {"ocaid": None, "providers": [{"url": "https://example.org/book", "access": "open-access", "format": "web"}]},
        ),
        Case(
            "partner:audio",
            "partner",
            {"ocaid": None, "providers": [{"url": "https://example.org/book", "access": "open-access", "format": "audio"}]},
        ),
        Case(
            "partner:sample",
            "partner",
            {"ocaid": None, "providers": [{"url": "https://example.org/book", "access": "sample", "format": "web"}]},
        ),
        Case(
            "partner:borrow",
            "partner",
            {"ocaid": None, "providers": [{"url": "https://example.org/book", "access": "borrow", "format": "web"}]},
            comment="read_button.html has no $else -- this renders nothing at all",
        ),
        Case("open", "open", {"availability": {"is_readable": True}}),
        Case("printdisabled:special", "printdisabled", {"availability": {"is_printdisabled": True}}),
        Case(
            "printdisabled:special-no-aux",
            "printdisabled",
            {"availability": {}},
            comment="neither is_printdisabled nor is_lendable, so the book page suppresses Preview too",
        ),
        Case("printdisabled:borrow", "printdisabled", {"availability": {"is_printdisabled": True, **LENDABLE, "available_to_borrow": True}}),
        Case("printdisabled:read", "printdisabled", {"availability": {**LENDABLE, "available_to_browse": True}}),
        Case("borrowable", "borrowable", {"availability": {**LENDABLE, "available_to_borrow": True}}),
        Case("waitlist:new", "waitlist", {"availability": {**LENDABLE, "available_to_waitlist": True, "users_on_waitlist": 3}}),
        Case(
            "waitlist:held",
            "waitlist",
            {"availability": {**LENDABLE, "users_on_waitlist": 3}},
            waiting_loan={"position": 2, "wl_size": 5},
            comment="a signed-in reader who already holds a spot; only the book page passes check_loan_status",
        ),
        Case("checkedout", "checkedout", {"availability": LENDABLE}),
        Case("preview_only", "preview_only", {"availability": {"is_previewable": True}}),
        Case("locate:edition", "locate", {}),
        Case("locate:work", "locate", {"key": WORK_KEY, "works": None}),
    )
}

# Cases where the macro is known to resolve no control at all today.  Each one
# is a real hole, not a fixture artefact; the parametrised test below xfails
# strictly on them so that closing a hole fails loudly and the entry gets
# deleted along with the fix.
KNOWN_HOLES = {
    "partner:borrow": "read_button.html has no $else for access='borrow' (book_providers.py:229)",
}


# ---------------------------------------------------------------------------
# Actions -- what a reader can do, and the one place each one's markup lives.
# The matrix below names actions; only this section knows any HTML.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Markup:
    """One shape an action takes in the DOM.

    ``href`` interpolates {ocaid}, {edition} and {work}; None means the control
    is not a link.  An action rendered by more than one macro (Preview has
    three) lists each shape, and any one of them counts as that action.
    """

    selector: str
    label: str
    href: str | None = None


class Action:
    """Something the reader can do, named once and referred to by name."""

    def __init__(self, name: str, *markups: Markup):
        self.name = name
        self.markups = markups

    def __repr__(self) -> str:
        return self.name


class Note:
    """Prose, not an affordance -- kept apart from actions deliberately: a bare
    note is exactly what #13314 left where a button used to be."""

    def __init__(self, name: str, selector: str, prefix: str):
        self.name = name
        self.selector = selector
        self.prefix = prefix

    def __repr__(self) -> str:
        return self.name


READ = Action(
    "READ",
    Markup("a.cta-btn--read", "Read", "/borrow/ia/{ocaid}?ref=ol"),
    Markup("a.cta-btn--read", "Read", "/books/{edition}/-/borrow?action=read"),  # partner provider
)
BORROW = Action("BORROW", Markup("a.cta-btn--borrow", "Borrow", "/borrow/ia/{ocaid}?ref=ol"))
SPECIAL_ACCESS = Action("SPECIAL_ACCESS", Markup("a.cta-btn--read", "Special Access", "/borrow/ia/{ocaid}?ref=ol"))
AUDIOBOOK = Action("AUDIOBOOK", Markup("a.cta-btn--read", "Audiobook", "/books/{edition}/-/borrow?action=read"))
PREVIEW = Action(
    "PREVIEW",
    Markup("ol-button.preview-btn", "Preview"),  # book page, beside Search
    Markup("a.cta-btn--preview", "Preview Only", "#bookPreview"),  # BookPreview CTA
    Markup("a.cta-btn--shell", "Preview", "/books/{edition}/-/borrow?action=read"),  # partner sample
)
SEARCH_INSIDE = Action("SEARCH_INSIDE", Markup("ol-button.search-inside-trigger-btn", "Search"))
LISTEN = Action("LISTEN", Markup(".dropper-menu a", "Listen", "/borrow/ia/{ocaid}?ref=ol&_autoReadAloud=show"))
LOCATE = Action("LOCATE", Markup("a.cta-btn--external", "Locate", "/books/{edition}/-/borrow?action=locate"))
JOIN_WAITLIST = Action("JOIN_WAITLIST", Markup("input#waitlist_ebook", "Join Waitlist"))
LEAVE_WAITLIST = Action("LEAVE_WAITLIST", Markup("input#unwaitlist_ebook", "Leave waiting list"))
RETURN = Action("RETURN", Markup(".return-form input[type=submit]", "Return book"))
CHECKED_OUT = Action("CHECKED_OUT", Markup("a.cta-btn--missing", "Checked Out", "{work}"))
NOT_IN_LIBRARY = Action("NOT_IN_LIBRARY", Markup("span.cta-btn--no-pointer", "Not in Library"))

ACTIONS = (
    READ,
    BORROW,
    SPECIAL_ACCESS,
    AUDIOBOOK,
    PREVIEW,
    SEARCH_INSIDE,
    LISTEN,
    LOCATE,
    JOIN_WAITLIST,
    LEAVE_WAITLIST,
    RETURN,
    CHECKED_OUT,
    NOT_IN_LIBRARY,
)

ONLY_PREVIEW = Note("only_preview", "p.waitinglist-message", "Only a preview is available")
READERS_IN_LINE = Note("readers_in_line", "p.waitinglist-message", "Readers in line")
YOUR_POSITION = Note("your_position", "p.waitinglist-message", "You are")
LOAN_EXPIRY = Note("loan_expiry", "div.local-date-time", "Expires")

NOTES = (ONLY_PREVIEW, READERS_IN_LINE, YOUR_POSITION, LOAN_EXPIRY)


# ---------------------------------------------------------------------------
# The matrix
# ---------------------------------------------------------------------------

# A control is auxiliary when it renders inside the secondary_action block, the
# "more reading options" dropper, or the return form; the primary call to action
# is whatever is left.  Two rows resolve no primary at all: partner:borrow is a
# known hole, and preview_only on the book page leans on the Preview button that
# the secondary block happens to supply -- the shape #13314 left everywhere else.

# fmt: off
MATRIX = (
    # case key                       surfaces        primary          auxiliary                                         notes
    ("borrowed",                     BOOK_PAGE,      READ,            (PREVIEW, SEARCH_INSIDE, LISTEN, LOCATE, RETURN), (LOAN_EXPIRY,)),
    ("borrowed",                     LISTS,          READ,            (LISTEN, LOCATE),                                 ()),
    ("borrowed",                     CAROUSEL,       READ,            (),                                               ()),

    ("partner:open-access",          ANY,            READ,            (),                                               ()),
    ("partner:audio",                ANY,            AUDIOBOOK,       (),                                               ()),
    ("partner:sample",               ANY,            PREVIEW,         (),                                               ()),
    ("partner:borrow",               ANY,            None,            (),                                               ()),  # hole: KNOWN_HOLES

    ("open",                         BOOK_PAGE,      READ,            (PREVIEW, SEARCH_INSIDE, LISTEN, LOCATE),         ()),
    ("open",                         LISTS,          READ,            (LISTEN, LOCATE),                                 ()),
    ("open",                         CAROUSEL,       READ,            (),                                               ()),

    ("printdisabled:special",        BOOK_PAGE,      SPECIAL_ACCESS,  (PREVIEW, SEARCH_INSIDE, LISTEN, LOCATE),         ()),
    ("printdisabled:special",        LISTS,          SPECIAL_ACCESS,  (LISTEN, LOCATE),                                 ()),
    ("printdisabled:special",        CAROUSEL,       SPECIAL_ACCESS,  (),                                               ()),

    ("printdisabled:special-no-aux", BOOK_PAGE,      SPECIAL_ACCESS,  (LISTEN, LOCATE),                                 ()),  # no Preview
    ("printdisabled:special-no-aux", LISTS,          SPECIAL_ACCESS,  (LISTEN, LOCATE),                                 ()),
    ("printdisabled:special-no-aux", CAROUSEL,       SPECIAL_ACCESS,  (),                                               ()),

    ("printdisabled:borrow",         BOOK_PAGE,      BORROW,          (PREVIEW, SEARCH_INSIDE, LISTEN, LOCATE),         ()),
    ("printdisabled:borrow",         LISTS,          BORROW,          (LISTEN, LOCATE),                                 ()),
    ("printdisabled:borrow",         CAROUSEL,       BORROW,          (),                                               ()),

    ("printdisabled:read",           BOOK_PAGE,      READ,            (PREVIEW, SEARCH_INSIDE, LISTEN, LOCATE),         ()),
    ("printdisabled:read",           LISTS,          READ,            (LISTEN, LOCATE),                                 ()),
    ("printdisabled:read",           CAROUSEL,       READ,            (),                                               ()),

    ("borrowable",                   BOOK_PAGE,      BORROW,          (PREVIEW, SEARCH_INSIDE, LISTEN, LOCATE),         ()),
    ("borrowable",                   LISTS,          BORROW,          (LISTEN, LOCATE),                                 ()),
    ("borrowable",                   CAROUSEL,       BORROW,          (),                                               ()),

    ("waitlist:new",                 BOOK_PAGE,      JOIN_WAITLIST,   (PREVIEW, SEARCH_INSIDE),                         (READERS_IN_LINE,)),
    ("waitlist:new",                 OFF_BOOK_PAGE,  JOIN_WAITLIST,   (),                                               ()),

    ("waitlist:held",                BOOK_PAGE,      LEAVE_WAITLIST,  (PREVIEW, SEARCH_INSIDE),                         (YOUR_POSITION,)),
    ("waitlist:held",                OFF_BOOK_PAGE,  JOIN_WAITLIST,   (),                                               ()),  # wrong: already #2

    ("checkedout",                   BOOK_PAGE,      CHECKED_OUT,     (PREVIEW, SEARCH_INSIDE),                         ()),
    ("checkedout",                   OFF_BOOK_PAGE,  CHECKED_OUT,     (),                                               ()),

    ("preview_only",                 BOOK_PAGE,      None,            (PREVIEW, SEARCH_INSIDE),                         (ONLY_PREVIEW,)),
    ("preview_only",                 OFF_BOOK_PAGE,  PREVIEW,         (),                                               ()),

    ("locate:edition",               ANY,            LOCATE,          (),                                               ()),
    ("locate:work",                  BOOK_PAGE,      LOCATE,          (),                                               ()),
    ("locate:work",                  OFF_BOOK_PAGE,  NOT_IN_LIBRARY,  (),                                               ()),
)
# fmt: on


@dataclass(frozen=True)
class Rendered:
    """What one render resolved to, in document order."""

    primary: tuple[Action, ...]
    auxiliary: tuple[Action, ...]
    notes: tuple[Note, ...]


def _cells():
    """Flatten MATRIX to one (case, surface, expected) per call site."""
    for case_key, surfaces, primary, auxiliary, notes in MATRIX:
        for name in (surfaces,) if isinstance(surfaces, str) else surfaces:
            expected = Rendered(() if primary is None else (primary,), auxiliary, notes)
            yield pytest.param(CASES[case_key], SURFACES[name], expected, id=f"{case_key}-{name}")


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


class FakeUser:
    """The slice of the user object LoanStatus and ReadButton actually touch."""

    def __init__(self, waiting_loan=None):
        self._waiting_loan = waiting_loan

    def get_user_waiting_loans(self, ocaid, use_cache=True):
        return self._waiting_loan

    def get_loan_for(self, ocaid, use_cache=True):
        return None

    def is_printdisabled(self):
        return False


# Who get_current_user() reports for the render in progress.  A macro bakes a
# copy of Template.globals into its compiled environment, so the indirection
# has to be installed before load_macros(); only this cell varies per case.
_SIGNED_IN: dict[str, FakeUser | None] = {"user": None}


def _get_current_user() -> FakeUser | None:
    return _SIGNED_IN["user"]


@pytest.fixture
def loan_status_env(mock_site, render_template, request_context_fixture):
    """Everything LoanStatus needs that the bare render_template fixture lacks."""
    request_context_fixture(lang="en")
    globals_ = web.template.Template.globals
    original_get_current_user = globals_.get("get_current_user")
    globals_["get_current_user"] = _get_current_user
    # load_macros re-registers every macro as lazy, so they recompile against
    # the globals installed above.
    macro.load_macros("openlibrary", lazy=True)
    # query_param('debug') in the macro's timing block reads the raw WSGI env.
    web.ctx.env.setdefault("REQUEST_METHOD", "GET")
    web.ctx.env.setdefault("QUERY_STRING", "")
    # ReturnForm posts back to $request.fullpath.
    web.ctx.fullpath = REQUEST_PATH
    globals_["request"] = web.ctx

    yield

    _SIGNED_IN["user"] = None
    if original_get_current_user is not None:
        globals_["get_current_user"] = original_get_current_user
    macro.load_macros("openlibrary", lazy=True)


def render_case(case: Case, surface: Surface) -> tuple[str, dict[str, str]]:
    """Render one cell, with the values its hrefs are built from."""
    # render_once() keys off web.ctx, so reset it: every cell is a fresh request.
    web.ctx.pop("render_once", None)
    _SIGNED_IN["user"] = FakeUser(case.waiting_loan) if case.waiting_loan else None
    doc = case.build_doc()
    try:
        html = str(macro.macrostore["LoanStatus"](doc, lending_state=case.state, **surface.kwargs))
    finally:
        _SIGNED_IN["user"] = None
    return html, {"ocaid": OCAID, "edition": doc["key"].split("/")[2], "work": WORK_KEY}


# ---------------------------------------------------------------------------
# Recognition -- markup back to action names
# ---------------------------------------------------------------------------

# Anything matching this that no action claims is an unnamed control, which
# fails the render rather than passing unnoticed.
CONTROL_SELECTOR = "a[href], button, ol-button, input[type=submit], span.cta-btn"

# Subtrees belonging to something already named: the preview dialog is a
# page-level singleton (audit F-7), and the form is SEARCH_INSIDE's own panel.
IGNORED_SELECTOR = "ol-dialog, form.search-inside-form"

# A control inside one of these sits beside the call to action rather than
# being it: the secondary_action block, the dropper, the return form.
AUXILIARY_CLASSES = frozenset({"book-preview-buttons", "return-form"})


def _label(el: Tag) -> str:
    if el.name == "input":
        return el.get("value", "")
    return " ".join(el.get_text(" ", strip=True).split())


def _is_auxiliary(el: Tag) -> bool:
    return any(p.name == "details" or AUXILIARY_CLASSES & set(p.get("class") or []) for p in el.parents)


def _claims(soup: BeautifulSoup, ctx: dict[str, str]) -> dict[int, Action | Note]:
    """Which element is which action, going only by the registries above."""
    claimed: dict[int, Action | Note] = {}
    for action in ACTIONS:
        for markup in action.markups:
            href = markup.href and markup.href.format(**ctx)
            for el in soup.select(markup.selector):
                if _label(el) != markup.label or (href is not None and el.get("href") != href):
                    continue
                assert claimed.get(id(el), action) is action, f"<{el.name}> claimed by both {claimed[id(el)]} and {action}"
                claimed[id(el)] = action
    for note in NOTES:
        for el in soup.select(note.selector):
            if _label(el).startswith(note.prefix):
                claimed[id(el)] = note
    return claimed


def recognise(html: str, ctx: dict[str, str]) -> Rendered:
    soup = BeautifulSoup(html, "lxml")
    for ignored in soup.select(IGNORED_SELECTOR):
        ignored.decompose()

    claimed = _claims(soup, ctx)
    controls = {id(el) for el in soup.select(CONTROL_SELECTOR)}
    primary: list[Action] = []
    auxiliary: list[Action] = []
    notes: list[Note] = []

    for el in soup.find_all(True):
        match claimed.get(id(el)):
            case Note() as note:
                notes.append(note)
            case Action() as action:
                (auxiliary if _is_auxiliary(el) else primary).append(action)
            case None if id(el) in controls:
                raise AssertionError(f"control no action claims: <{el.name} class={el.get('class')}> {_label(el)!r} href={el.get('href')!r}")

    return Rendered(tuple(primary), tuple(auxiliary), tuple(notes))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("case", "surface", "expected"), _cells())
def test_matrix(loan_status_env, case, surface, expected):
    """Every cell renders the actions the matrix says it does.

    The table does not claim the behaviour is right: partner:borrow renders
    nothing at all, and waitlist:held offers a reader already in the queue
    "Join Waitlist" again on every surface but the book page.  It claims the
    behaviour is *known*, so that changing it is a one-row diff.
    """
    html, ctx = render_case(case, surface)
    assert recognise(html, ctx) == expected


def test_matrix_covers_every_cell():
    """No (case, surface) may go missing from the table, or be listed twice."""
    listed = [(key, name) for key, surfaces, *_ in MATRIX for name in ((surfaces,) if isinstance(surfaces, str) else surfaces)]
    assert sorted(listed) == sorted((key, name) for key in CASES for name in SURFACES)


@pytest.mark.parametrize(
    ("case", "surface"),
    [
        pytest.param(
            case,
            surface,
            id=f"{case.key}-{surface.name}",
            marks=[pytest.mark.xfail(strict=True, reason=KNOWN_HOLES[case.key])] if case.key in KNOWN_HOLES else [],
        )
        for case in CASES.values()
        for surface in SURFACES.values()
    ],
)
def test_every_case_offers_a_control(loan_status_env, case, surface):
    """Every case, on every surface, must resolve at least one control.

    This is the assertion #13314 could not fail: it deleted the only control in
    the preview_only branch and left a note behind, which reads like markup but
    offers the reader nothing to click.  It still fails today for
    partner:borrow, which is xfailed above rather than hidden.
    """
    html, ctx = render_case(case, surface)
    rendered = recognise(html, ctx)
    assert rendered.primary or rendered.auxiliary, f"{case.key} on {surface.name} ({surface.call_site}) offers only {rendered.notes or 'nothing'}"
