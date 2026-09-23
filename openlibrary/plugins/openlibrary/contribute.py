"""First Edits pages at /contribute: a guided first contribution.

Phase 1 is a click-through walkthrough. Book records and sibling editions
are live; outside evidence, practice and status states come from fixtures in
openlibrary/first_edits/fixtures; nothing is saved. Every page except the
start page is for beta testers and admins while it is tried out.
"""

from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import urlencode

import web

from infogami.utils import delegate
from infogami.utils.view import query_param, render_template
from openlibrary import accounts
from openlibrary.first_edits import fixtures, tasks
from openlibrary.first_edits import practice as practice_mod
from openlibrary.first_edits.playbooks import get_playbooks, link_outs
from openlibrary.first_edits.scope import load_scope
from openlibrary.first_edits.siblings import SiblingValue, sibling_counts_for_edition
from openlibrary.first_edits.sources import get_sources
from openlibrary.i18n import gettext as _
from openlibrary.plugins.upstream.mybooks import ReadingLog

DENIED = "First Edits is being tried out with a small group"
SHELVES: tuple[Literal["want-to-read", "currently-reading", "already-read"], ...] = ("want-to-read", "currently-reading", "already-read")

# The Jinja page for each handler. Listed in full so template usage is greppable.
PAGES = {
    "start": "contribute/start.html.jinja",
    "index": "contribute/index.html.jinja",
    "task": "contribute/task.html.jinja",
    "nothing": "contribute/nothing.html.jinja",
    "done": "contribute/done.html.jinja",
    "practice": "contribute/practice.html.jinja",
    "mine": "contribute/mine.html.jinja",
    "review": "contribute/review.html.jinja",
}


def setup():
    pass


@dataclass
class PageData:
    template: str
    title: str
    params: dict = field(default_factory=dict)


def _render(page: str, title: str, **params):
    return render_template("contribute", PageData(PAGES[page], title, params))


def _user():
    return accounts.get_current_user()


def _allowed(user) -> bool:
    return bool(user and (user.is_beta_tester() or user.is_admin()))


def _denied(path: str):
    return render_template("permission_denied", path, DENIED)


def _language_names(codes: set[str]) -> dict[str, str]:
    names = {}
    for code in codes:
        if lang := web.ctx.site.get(f"/languages/{code}"):
            names[code] = lang.name or code
    return names


def _language_names_for(edition, evidence_doc: dict | None) -> dict[str, str]:
    codes = set(tasks.edition_values(edition)["languages"])
    for src in (evidence_doc or {}).get("sources", []):
        codes.update(src.get("fields", {}).get("languages") or [])
    return _language_names(codes)


def _cover_url(edition, isbn: str | None) -> str | None:
    """Prefer the production cover for a demo book: dev cover ids point at the wrong images."""
    if isbn and (cover_id := fixtures.demo_cover_id(isbn)):
        return f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg"
    return edition.get_cover_url("M")


def _book(edition, readers: int | None = None) -> dict:
    """What the book header shows. Live from the local record."""
    work = edition.works[0] if edition.works else None
    year = edition.get_publish_year()
    parts = [p for p in [", ".join(edition.get("publishers") or []), str(year) if year else "", edition.get("physical_format") or ""] if p]
    isbn = edition.get_isbn13()
    seen: set[str] = set()
    author_names = []
    for a in edition.get_authors():
        if a and a.get("name") and a.key not in seen:
            seen.add(a.key)
            author_names.append(a.name)
    return {
        "key": edition.key,
        "olid": edition.key.split("/")[-1],
        "title": edition.get_title(),
        "authors": ", ".join(author_names),
        "cover_url": _cover_url(edition, isbn),
        "edition_line": " · ".join(parts),
        "isbn13": isbn,
        "edition_count": work.get_edition_count() if work else 1,
        "work_key": work.key if work else None,
        "readers": readers if readers is not None else fixtures.demo_readers(isbn),
    }


def _edition_by_isbn(isbn13: str):
    keys = web.ctx.site.things({"type": "/type/edition", "isbn_13": isbn13, "limit": 1})
    return web.ctx.site.get(keys[0]) if keys else None


def _demo_editions() -> list:
    out = []
    for entry in fixtures.load_demo_books():
        if ed := _edition_by_isbn(entry["isbn13"]):
            out.append((ed, entry.get("readers", 0)))
    return out


def _shelf_editions(user) -> list:
    """The user's logged works, each reduced to one edition worth checking."""
    out = []
    seen = set()
    log = ReadingLog(user=user)
    for shelf in SHELVES:
        data = log.get_works(shelf, limit=50)
        for doc in data.docs:
            work_key = doc.get("key")
            if not work_key or work_key in seen:
                continue
            seen.add(work_key)
            work = web.ctx.site.get(work_key)
            if not work:
                continue
            editions = work.get_sorted_editions()
            with_evidence = [e for e in editions if e.get_isbn13() and fixtures.load_evidence(e.get_isbn13())]
            pick = with_evidence[0] if with_evidence else next((e for e in editions if e.get_isbn13()), None)
            if pick:
                out.append((pick, None))
    return out


def _level_label(level: str) -> str:
    return {
        "strong": _("Strong evidence"),
        "fair": _("Fair evidence"),
        "weak": _("Weak evidence"),
        "none": _("No outside evidence"),
    }.get(level, "")


def _match_label(match: str) -> str:
    return _("found by exact ISBN") if match in ("isbn13", "isbn10", "lccn", "oclc") else _("matched by title and author")


def _evidence_view(ev, sources) -> dict:
    """A plain dict for the templates, which never call functions on their data."""
    rows = []
    for v in ev.values:
        src = sources.get(v.source)
        rows.append(
            {
                "id": v.source,
                "name": src.name if src else v.source,
                "kind": src.kind if src else "",
                "blurb": src.blurb if src else "",
                "why": src.why_trusted if src else "",
                "display": v.display,
                "match_label": _match_label(v.match),
                "url": v.url,
                "agrees": v.agrees_with_ol,
            }
        )
    names = [r["name"] for r in rows if r["id"] in ev.suggestion_sources]
    return {
        "field": ev.field,
        "verdict": ev.verdict,
        "level": ev.level,
        "level_label": _level_label(ev.level),
        "sentence": ev.sentence,
        "ol_display": ev.ol_display,
        "suggestion_display": ev.suggestion_display,
        "suggestion_sources_label": _(" and ").join(names),
        "rows": rows,
    }


def _task_summary(task: tasks.Task, playbooks) -> dict:
    return {
        "key": task.key,
        "field": task.field,
        "label": playbooks[task.field].label,
        "mode": task.mode,
        "level": task.evidence.level,
        "level_label": _level_label(task.evidence.level),
        "quick_win": task.quick_win,
        "url": f"/contribute/task/{task.olid}/{task.field}",
    }


def _rows(editions: list, quick: bool) -> list[dict]:
    playbooks = get_playbooks()
    scope = load_scope()
    rows = []
    for edition, readers in editions:
        names = _language_names_for(edition, tasks.evidence_for_edition(edition))
        ts = tasks.tasks_for_edition(edition, scope, names)
        if quick:
            ts = [t for t in ts if t.quick_win]
        if not ts:
            continue
        rows.append({"book": _book(edition, readers), "tasks": [_task_summary(t, playbooks) for t in ts]})
    return rows


class contribute_start(delegate.page):
    path = "/contribute/start"

    def GET(self):
        user = _user()
        return _render(
            "start",
            _("Make your first edit"),
            wait_days=load_scope().review_wait_days,
            allowed=_allowed(user),
            logged_in=bool(user),
            came_from=query_param("from", ""),
        )


class contribute_index(delegate.page):
    path = "/contribute"

    def GET(self):
        user = _user()
        if not _allowed(user):
            return _denied(self.path)
        view = query_param("view", "popular")
        quick = query_param("quick", "") == "1"
        editions = _shelf_editions(user) if view == "shelves" else _demo_editions()
        return _render(
            "index",
            _("Books that need a hand"),
            view=view,
            quick=quick,
            rows=_rows(editions, quick),
            status_counts={"pending": 1, "accepted": 1},
        )


def _task_context(edition, task: tasks.Task, names: dict[str, str]) -> dict:
    playbooks = get_playbooks()
    playbook = playbooks[task.field]
    siblings, sibling_total = sibling_counts_for_edition(edition, task.field)
    book = _book(edition)
    ev = task.evidence
    sources = get_sources()
    note = _prefilled_note(ev, sources, siblings)
    return {
        "book": book,
        "task": {"key": task.key, "field": task.field, "mode": task.mode, "quick_win": task.quick_win, "url": f"/contribute/task/{task.olid}/{task.field}"},
        "playbook": playbook,
        "question": playbook.question(task.mode),
        "evidence": _evidence_view(ev, sources),
        "siblings": siblings,
        "sibling_total": sibling_total,
        "sibling_suggestions": [s.display for s in siblings],
        "link_outs": link_outs(book["isbn13"], book["title"]),
        "note": note,
        "wait_days": load_scope().review_wait_days,
    }


def _prefilled_note(ev, sources, siblings: list[SiblingValue]) -> str:
    names = [sources[v.source].name for v in ev.values if v.source in sources]
    if not names or not ev.suggestion_display:
        return ""
    parts = [_("Matched %(sources)s by ISBN.", sources=_(" and ").join(names))]
    if siblings and siblings[0].display == ev.suggestion_display:
        parts.append(_("Other editions of this work use the same spelling."))
    return " ".join(parts)


class contribute_task(delegate.page):
    path = r"/contribute/task/(OL\d+M)/(languages|number_of_pages|publishers|subtitle|publish_date)"

    def GET(self, olid, fld):
        user = _user()
        if not _allowed(user):
            return _denied(f"/contribute/task/{olid}/{fld}")
        edition = web.ctx.site.get(f"/books/{olid}")
        if not edition or edition.type.key != "/type/edition":
            raise web.notfound()
        names = _language_names_for(edition, tasks.evidence_for_edition(edition))
        task = tasks.task_for(edition, fld, language_names=names)
        if not task:
            return _render("nothing", _("Nothing to check here"), book=_book(edition), field_label=get_playbooks()[fld].label)
        return _render("task", get_playbooks()[fld].question(task.mode), **_task_context(edition, task, names))

    def POST(self, olid, fld):
        user = _user()
        if not _allowed(user):
            return _denied(f"/contribute/task/{olid}/{fld}")
        i = web.input(choice="", value="", note="")
        # Phase 1: nothing is saved. The receipt is rendered from what was posted.
        query = urlencode({"choice": i.choice, "value": i.value.strip(), "note": i.note.strip()})
        raise web.seeother(f"/contribute/task/{olid}/{fld}/done?{query}")


class contribute_done(delegate.page):
    path = r"/contribute/task/(OL\d+M)/(languages|number_of_pages|publishers|subtitle|publish_date)/done"

    def GET(self, olid, fld):
        user = _user()
        if not _allowed(user):
            return _denied(f"/contribute/task/{olid}/{fld}/done")
        edition = web.ctx.site.get(f"/books/{olid}")
        if not edition:
            raise web.notfound()
        names = _language_names_for(edition, tasks.evidence_for_edition(edition))
        playbooks = get_playbooks()
        task = tasks.task_for(edition, fld, language_names=names)
        choice = query_param("choice", "")
        value = query_param("value", "")
        ev = task.evidence if task else tasks.field_evidence(edition, fld, names)
        if choice == "suggestion":
            new_value = ev.suggestion_display
        elif choice == "keep":
            new_value = ev.ol_display
        elif choice == "unsure":
            new_value = ""
        else:
            new_value = value
        same_book = [_task_summary(t, playbooks) for t in tasks.tasks_for_edition(edition, language_names=names) if t.field != fld]
        next_book = None
        for other, _readers in _demo_editions():
            if other.key == edition.key:
                continue
            other_names = _language_names_for(other, tasks.evidence_for_edition(other))
            if other_tasks := tasks.tasks_for_edition(other, language_names=other_names):
                next_book = {"book": _book(other), "task": _task_summary(other_tasks[0], playbooks)}
                break
        return _render(
            "done",
            _("Sent to a librarian"),
            book=_book(edition),
            field_label=playbooks[fld].label,
            choice=choice,
            old_value=ev.ol_display,
            new_value=new_value,
            note=query_param("note", ""),
            same_book=same_book,
            next_book=next_book,
            wait_days=load_scope().review_wait_days,
            task_key=f"{olid}/{fld}",
        )


class contribute_practice(delegate.page):
    path = "/contribute/practice"

    def _context(self, practice: dict) -> dict:
        playbooks = get_playbooks()
        names = _language_names(
            {c for src in practice["evidence"]["sources"] for c in src["fields"].get("languages", [])} | set(practice["ol_values"].get("languages", []))
        )
        ev = practice_mod.practice_evidence(practice, names)
        # A conflict has no mode of its own; ask as a fill when the field is empty, else as a check.
        mode = ev.mode or ("fill" if not ev.ol_display else "check")
        playbook = playbooks[practice["field"]]
        cover_id = practice.get("cover_id")
        book = {
            "key": None,
            "olid": None,
            "title": practice["title"],
            "authors": practice["authors"],
            "cover_url": f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg" if cover_id else None,
            "edition_line": practice["edition_line"],
            "isbn13": practice["isbn13"],
            "edition_count": practice.get("sibling_total", 0) + 1,
            "readers": practice.get("readers", 0),
        }
        siblings = [SiblingValue(s["display"], s["count"]) for s in practice.get("siblings", [])]
        sources = get_sources()
        return {
            "practice": {"key": practice["key"], "order": practice.get("order", 1), "total": len(fixtures.load_practice())},
            "book": book,
            "task": {
                "key": f"practice/{practice['key']}",
                "field": practice["field"],
                "mode": mode,
                "quick_win": False,
                "url": f"/contribute/practice?key={practice['key']}",
            },
            "playbook": playbook,
            "question": playbook.question(mode),
            "evidence": _evidence_view(ev, sources),
            "siblings": siblings,
            "sibling_total": practice.get("sibling_total", 0),
            "sibling_suggestions": [s.display for s in siblings],
            "link_outs": link_outs(practice["isbn13"], practice["title"]),
            "note": _prefilled_note(ev, sources, siblings),
            "wait_days": load_scope().review_wait_days,
        }

    def GET(self):
        user = _user()
        if not _allowed(user):
            return _denied(self.path)
        key = query_param("key", "")
        practice = fixtures.get_practice(key) or (fixtures.load_practice() or [None])[0]
        if not practice:
            raise web.notfound()
        return _render("practice", _("Practice book"), **self._context(practice), verdict=None, next_practice=None)

    def POST(self):
        user = _user()
        if not _allowed(user):
            return _denied(self.path)
        i = web.input(key="", choice="", value="", note="")
        practice = fixtures.get_practice(i.key)
        if not practice:
            raise web.notfound()
        verdict = practice_mod.judge(practice, i.choice, i.value)
        nxt = practice_mod.next_practice(practice["key"])
        return _render(
            "practice",
            _("Practice book"),
            **self._context(practice),
            verdict=verdict,
            next_practice={"key": nxt["key"], "title": nxt["title"]} if nxt else None,
        )


class contribute_mine(delegate.page):
    path = "/contribute/mine"

    def GET(self):
        user = _user()
        if not _allowed(user):
            return _denied(self.path)
        items = fixtures.load_status()
        return _render(
            "mine",
            _("Your suggestions"),
            suggestions=items,
            counts={s: sum(1 for it in items if it["state"] == s) for s in ("pending", "accepted", "declined")},
            wait_days=load_scope().review_wait_days,
        )


class contribute_review_preview(delegate.page):
    path = "/contribute/review-preview"

    def GET(self):
        user = _user()
        if not _allowed(user):
            return _denied(self.path)
        pending = next((it for it in fixtures.load_status() if it["state"] == "pending"), None)
        evidence = None
        if pending and (edition := web.ctx.site.get(pending["book_key"])):
            names = _language_names_for(edition, tasks.evidence_for_edition(edition))
            evidence = tasks.field_evidence(edition, pending["field"], names)
        return _render(
            "review",
            _("What a librarian sees"),
            item=pending,
            evidence=_evidence_view(evidence, get_sources()) if evidence else None,
            open_count=214,
            median_days=2.1,
        )
