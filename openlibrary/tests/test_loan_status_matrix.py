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

This module renders the macro for every reachable case against each of its four
real call sites, reduces each render to the controls a reader would actually
see, and diffs that against a committed snapshot.  Losing a button becomes a
one-line diff rather than a code-review judgement call.

After changing LoanStatus on purpose, rewrite the snapshot with::

    docker compose run --rm home bash -c \\
      "UPDATE_SNAPSHOTS=1 pytest openlibrary/tests/test_loan_status_matrix.py"

That rewrites the file and then fails once, printing the diff, so a behaviour
change cannot be regenerated away without someone reading it.  Re-run without
UPDATE_SNAPSHOTS to go green, and commit the snapshot with your change.
"""

import difflib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, NamedTuple

import pytest
import web
from bs4 import BeautifulSoup, Tag

from infogami.utils import macro

SNAPSHOT_PATH = Path(__file__).parent / "snapshots" / "loan_status_matrix.txt"

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


SURFACES = (
    # databarWork passes allow_expensive_availability_check too; it is omitted
    # here because it triggers a network call and -- per the audit's F-1 -- can
    # no longer change which branch is taken anyway.
    Surface("book_page", "macros/databarWork.html:39", {"secondary_action": True, "check_loan_status": True}),
    Surface("editions_table", "templates/books/edition-sort.html:93", {"is_book_page": True}),
    Surface("search_row", "macros/SearchResultsWork.html:253", {"work_key": WORK_KEY}),
    Surface(
        "carousel",
        "templates/books/custom_carousel_card.html:87",
        {"work_key": WORK_KEY, "listen": False, "analytics_override": "BookCarousel|{action}Click|OL1W"},
    ),
)


# ---------------------------------------------------------------------------
# Cases -- one row per reachable (lending state, sub-condition) pair.
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

CASES = (
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

# Cases where the macro is known to resolve no control at all today.  Each one
# is a real hole, not a fixture artefact; the parametrised test below xfails
# strictly on them so that closing a hole fails loudly and the entry gets
# deleted along with the fix.
KNOWN_HOLES = {
    "partner:borrow": "read_button.html has no $else for access='borrow' (book_providers.py:229)",
}


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


def render_case(case: Case, surface: Surface) -> str:
    # render_once() keys off web.ctx, so reset it: every row is a fresh request.
    web.ctx.pop("render_once", None)
    _SIGNED_IN["user"] = FakeUser(case.waiting_loan) if case.waiting_loan else None
    try:
        return str(macro.macrostore["LoanStatus"](case.build_doc(), lending_state=case.state, **surface.kwargs))
    finally:
        _SIGNED_IN["user"] = None


# ---------------------------------------------------------------------------
# Reduction -- HTML down to the controls a reader sees
# ---------------------------------------------------------------------------


class Affordance(NamedTuple):
    role: str
    label: str
    href: str | None


# Roles that put something clickable, or an explicit unavailable-state label,
# in front of the reader.  A bare note ("Only a preview is available.") is not
# one: that is exactly what #13314 left behind when it deleted the button.
CONTROL_ROLES = frozenset({"link", "submit", "button", "ol-button", "menu", "search", "static"})


def _text(el: Tag) -> str:
    return " ".join(el.get_text(" ", strip=True).split())


def _classify(el: Tag) -> tuple[Affordance | None, bool]:
    """Return (affordance or None, whether to descend into this element)."""
    classes = el.get("class") or []
    if el.name == "ol-dialog":
        # A page-level singleton emitted as a side effect of the preview macros
        # (audit F-7), not an affordance of this book.
        return None, False
    if el.name == "form" and "search-inside-form" in classes:
        return Affordance("search", "Search inside", None), False
    if el.name == "a" and el.get("href"):
        return Affordance("link", _text(el), el["href"]), False
    if el.name == "input" and el.get("type") == "submit":
        return Affordance("submit", el.get("value", ""), None), False
    if el.name == "button":
        return Affordance("button", _text(el) or el.get("aria-label", ""), None), False
    if el.name == "ol-button":
        return Affordance("ol-button", _text(el), None), False
    if el.name == "summary":
        return Affordance("menu", el.get("aria-label", ""), None), False
    if el.name == "span" and "cta-btn" in classes:
        return Affordance("static", _text(el), None), False
    if el.name == "p" and "waitinglist-message" in classes:
        return Affordance("note", _text(el), None), False
    if el.name == "div" and "local-date-time" in classes:
        # The rendered text is relative to now ("Expires in 3 days"); keep the
        # fact that a due date is shown without dating the snapshot.
        return Affordance("note", "Expires <loan expiry>", None), False
    return None, True


def reduce_html(html: str) -> list[Affordance]:
    soup = BeautifulSoup(html, "lxml")
    found: list[Affordance] = []

    def walk(node: Tag) -> None:
        for child in node.children:
            if not isinstance(child, Tag):
                continue
            affordance, descend = _classify(child)
            if affordance:
                found.append(affordance)
            if descend:
                walk(child)

    walk(soup)
    return found


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------

SNAPSHOT_HEADER = """\
LoanStatus golden matrix
========================

Generated by openlibrary/tests/test_loan_status_matrix.py -- do not hand-edit.
Regenerate with: UPDATE_SNAPSHOTS=1 pytest openlibrary/tests/test_loan_status_matrix.py

One block per (case, group of surfaces that render identically).  Surfaces are
the four real call sites of macros/LoanStatus.html:
"""


def _surface_legend() -> list[str]:
    width = max(len(s.name) for s in SURFACES)
    return [f"  {s.name.ljust(width)}  {s.call_site}" for s in SURFACES]


def _format_affordances(affordances: list[Affordance]) -> list[str]:
    if not affordances:
        return ["      (nothing rendered)"]
    role_width = max(len(a.role) for a in affordances)
    label_width = max(len(a.label) for a in affordances)
    lines = []
    for role, label, href in affordances:
        line = f"      {role.ljust(role_width)}  {label.ljust(label_width) if href else label}"
        if href:
            line = f"{line}  {href}"
        lines.append(line.rstrip())
    return lines


def build_snapshot() -> str:
    lines = [SNAPSHOT_HEADER.rstrip("\n"), *_surface_legend(), ""]
    for case in CASES:
        groups: list[tuple[list[str], list[Affordance]]] = []
        for surface in SURFACES:
            affordances = reduce_html(render_case(case, surface))
            for names, existing in groups:
                if existing == affordances:
                    names.append(surface.name)
                    break
            else:
                groups.append(([surface.name], affordances))

        lines.append("-" * 78)
        lines.append(f"case  {case.key}")
        lines.append(f"state {case.state}")
        lines.append(f"doc   {json.dumps(case.doc_fields, sort_keys=True)}")
        if case.waiting_loan:
            lines.append(f"user  holds a waiting loan {json.dumps(case.waiting_loan, sort_keys=True)}")
        if case.comment:
            lines.append(f"note  {case.comment}")
        lines.append("-" * 78)
        for names, affordances in groups:
            lines.append(f"  [{', '.join(names)}]")
            lines.extend(_format_affordances(affordances))
            lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def test_matrix_matches_snapshot(loan_status_env):
    """Freeze what every case renders on every surface.

    This test does not claim the current behaviour is right: partner:borrow
    renders nothing at all, and waitlist:held offers a reader already in the
    queue "Join Waitlist" again on every surface but the book page.  It claims
    the behaviour is *known*, so that changing it is a reviewable diff.
    """
    actual = build_snapshot()
    committed = SNAPSHOT_PATH.read_text() if SNAPSHOT_PATH.exists() else ""
    diff = "".join(difflib.unified_diff(committed.splitlines(True), actual.splitlines(True), "committed", "rendered"))

    if os.environ.get("UPDATE_SNAPSHOTS") == "1":
        if not diff:
            return
        SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT_PATH.write_text(actual)
        # Rewriting and passing would let a behaviour change land unread, so
        # fail once with the diff.  Re-run without UPDATE_SNAPSHOTS to go green.
        pytest.fail(f"Snapshot rewritten. Review this before committing it:\n\n{diff}")

    assert committed, f"missing snapshot; create it with UPDATE_SNAPSHOTS=1 pytest {__file__}"
    assert not diff, f"LoanStatus renders differently than the committed matrix.\n\n{diff}\nIf intended: UPDATE_SNAPSHOTS=1 pytest {__file__}"


@pytest.mark.parametrize(
    ("case", "surface"),
    [
        pytest.param(
            case,
            surface,
            id=f"{case.key}-{surface.name}",
            marks=[pytest.mark.xfail(strict=True, reason=KNOWN_HOLES[case.key])] if case.key in KNOWN_HOLES else [],
        )
        for case in CASES
        for surface in SURFACES
    ],
)
def test_every_case_renders_a_control(loan_status_env, case, surface):
    """Every case, on every surface, must resolve at least one control.

    This is the assertion #13314 could not fail: it deleted the only control in
    the preview_only branch and left a note behind, which reads like markup but
    offers the reader nothing to click.  It still fails today for
    partner:borrow, which is xfailed above rather than hidden.
    """
    affordances = reduce_html(render_case(case, surface))
    controls = [a for a in affordances if a.role in CONTROL_ROLES]
    assert controls, f"{case.key} on {surface.name} ({surface.call_site}) rendered no control, only {affordances or 'nothing'}"
