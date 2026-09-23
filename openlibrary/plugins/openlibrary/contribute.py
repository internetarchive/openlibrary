"""First Edits pages at /contribute: a guided first contribution.

Phase 1 is a click-through walkthrough. Book records and sibling editions
are live; outside evidence and the demo set come from fixtures in
openlibrary/first_edits/fixtures; nothing is saved. Every page except the
start page is for beta testers and admins while it is tried out.
"""

from dataclasses import dataclass, field
from urllib.parse import urlencode

import web

from infogami.utils import delegate
from infogami.utils.view import query_param, render_template
from openlibrary import accounts
from openlibrary.first_edits import fixtures, tasks
from openlibrary.first_edits.playbooks import get_playbooks, link_outs
from openlibrary.first_edits.scope import load_scope
from openlibrary.first_edits.siblings import SiblingValue, sibling_counts_for_edition
from openlibrary.first_edits.sources import get_sources
from openlibrary.i18n import gettext as _
from openlibrary.utils.isbn import isbn_13_to_isbn_10

DENIED = "First Edits is being tried out with a small group"

# The Jinja page for each handler. Listed in full so template usage is greppable.
PAGES = {
    "start": "contribute/start.html.jinja",
    "index": "contribute/index.html.jinja",
    "task": "contribute/task.html.jinja",
    "nothing": "contribute/nothing.html.jinja",
    "done": "contribute/done.html.jinja",
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


def _sibling_view(fld: str, siblings: list[SiblingValue], ev) -> list[dict]:
    """Chips for the templates. Languages show names; a chip matching an answer on screen picks that answer."""
    names = _language_names({s.display for s in siblings}) if fld == "languages" else {}
    view = []
    for s in siblings:
        display = names.get(s.display, s.display)
        choices = []
        if ev.suggestion_display and display == ev.suggestion_display:
            choices.append("suggestion")
        if ev.ol_display and display == ev.ol_display:
            choices.append("keep")
        view.append({"value": s.display, "display": display, "count": s.count, "choices": " ".join(choices)})
    return view


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
    for fld, value in (("isbn_13", isbn13), ("isbn_10", isbn_13_to_isbn_10(isbn13))):
        if value and (keys := web.ctx.site.things({"type": "/type/edition", fld: value, "limit": 1})):
            return web.ctx.site.get(keys[0])
    return None


def _demo_editions() -> list:
    """Resolve by the production key in one batch; fall back to ISBN where the key is absent or another book (dev)."""
    entries = fixtures.load_demo_books()
    by_key = {ed.key: ed for ed in web.ctx.site.get_many([e["key"] for e in entries if e.get("key")])}
    out = []
    for entry in entries:
        ed = by_key.get(entry.get("key"))
        if not ed or ed.get_isbn13() != entry["isbn13"]:
            ed = _edition_by_isbn(entry["isbn13"])
        if ed:
            out.append((ed, entry.get("readers", 0)))
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
        "url": f"/contribute/task/{task.olid}/{task.field}",
    }


def _rows(editions: list) -> list[dict]:
    playbooks = get_playbooks()
    scope = load_scope()
    rows = []
    for edition, readers in editions:
        names = _language_names_for(edition, tasks.evidence_for_edition(edition))
        ts = tasks.tasks_for_edition(edition, scope, names)
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
        )


class contribute_index(delegate.page):
    path = "/contribute"

    def GET(self):
        user = _user()
        if not _allowed(user):
            return _denied(self.path)
        return _render("index", _("Books that need a hand"), rows=_rows(_demo_editions()))


def _task_context(edition, task: tasks.Task, names: dict[str, str]) -> dict:
    playbooks = get_playbooks()
    playbook = playbooks[task.field]
    siblings, sibling_total = sibling_counts_for_edition(edition, task.field)
    book = _book(edition)
    ev = task.evidence
    sources = get_sources()
    chips = _sibling_view(task.field, siblings, ev)
    note = _prefilled_note(ev, sources, chips)
    return {
        "book": book,
        "task": {"key": task.key, "field": task.field, "mode": task.mode, "url": f"/contribute/task/{task.olid}/{task.field}"},
        "playbook": playbook,
        "question": playbook.question(task.mode),
        "evidence": _evidence_view(ev, sources),
        "siblings": chips,
        "sibling_total": sibling_total,
        "link_outs": link_outs(book["isbn13"], book["title"]),
        "note": note,
        "wait_days": load_scope().review_wait_days,
    }


def _prefilled_note(ev, sources, chips: list[dict]) -> str:
    names = [sources[v.source].name for v in ev.values if v.source in sources]
    if not names or not ev.suggestion_display:
        return ""
    parts = [_("Matched %(sources)s by ISBN.", sources=_(" and ").join(names))]
    if chips and chips[0]["display"] == ev.suggestion_display:
        if ev.field == "languages":
            parts.append(_("Other editions of this work say the same."))
        else:
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
            wait_days=load_scope().review_wait_days,
            task_key=f"{olid}/{fld}",
        )
