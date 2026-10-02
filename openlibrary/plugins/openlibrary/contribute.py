"""First Edits pages at /contribute: a guided first contribution.

Phase 1 is a click-through walkthrough. Book records and sibling editions
are live; outside evidence and the demo set come from fixtures in
openlibrary/first_edits/fixtures; nothing is saved. Every page except the
start page is for beta testers and librarians while it is tried out.
"""

from dataclasses import dataclass, field
from urllib.parse import urlencode

import web

from infogami.utils import delegate
from infogami.utils.view import query_param, render_template
from openlibrary import accounts
from openlibrary.first_edits import fixtures, identifiers, tasks
from openlibrary.first_edits.playbooks import get_playbooks, link_outs
from openlibrary.first_edits.scope import load_scope
from openlibrary.first_edits.siblings import edition_field_values, sibling_counts
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
    """Beta testers, plus the groups that already try out new UI: librarians, maintainers, admins."""
    return bool(user and (user.is_beta_tester() or user.is_librarian_or_higher() or user.is_maintainer()))


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


def _sibling_list(fld: str, others: list, limit: int = 10) -> list[dict]:
    """One line per other edition: its value for this field, plus enough to tell the editions apart."""
    values = {e.key: edition_field_values(e, fld) for e in others}
    names = _language_names({str(v) for vs in values.values() for v in vs}) if fld == "languages" else {}
    rows = []
    for e in sorted(others, key=lambda e: not values[e.key])[:limit]:
        year = e.get_publish_year()
        about = [
            ", ".join(e.get("publishers") or []) if fld != "publishers" else "",
            str(year) if year and fld != "publish_date" else "",
            (e.get("physical_format") or "") if fld != "physical_format" else "",
        ]
        rows.append({"url": e.key, "value": ", ".join(names.get(str(v), str(v)) for v in values[e.key]), "about": ", ".join(p for p in about if p)})
    return rows


def _sibling_top(fld: str, others: list) -> str:
    """The most common value among the other editions, as the answers on screen display it."""
    if not (top := sibling_counts(others, fld, limit=1)):
        return ""
    return _language_names({top[0].display}).get(top[0].display, top[0].display) if fld == "languages" else top[0].display


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
        "action_label": playbooks[task.field].action(task.mode),
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


# A passing check is reassurance, not an alert: it stays a quiet line. Only a
# warning or a failure earns the ol-message treatment, so attention goes to problems.
CHECK_TONES = {"pass": ("", "circle-check"), "warn": ("warning", "triangle-alert"), "fail": ("error", "circle-alert")}


def _sibling_editions(edition) -> list:
    work = edition.works[0] if edition.works else None
    if not work:
        return []
    return [e for e in work.get_sorted_editions(keys=[edition.key]) if e.key != edition.key]


def _identifier_context(edition, task: tasks.Task, names: dict[str, str]) -> dict:
    """The record an identifier points at, the checks run against it, and the traps nobody can check.

    The number itself is not evidence: the Library of Congress record of course
    carries its own LCCN. What a newcomer can judge is whether that record
    describes the book on this page, so that comparison is the page.
    """
    spec = identifiers.get_specs()[task.field]
    values = tasks.edition_values(edition)
    doc = tasks.evidence_for_edition(edition) or {"sources": []}
    src, rows, match_check = tasks.corroboration(task.field, values, doc, names)
    value = ((src or {}).get("fields", {}).get(task.field) or [""])[0]
    sources = get_sources()
    source = sources.get((src or {}).get("id", ""))

    value, format_check = identifiers.check_format(spec, value)
    checks = [format_check, identifiers.check_collision(spec, value, _sibling_editions(edition)) if value else None, match_check]
    checks = [c for c in checks if c]
    caught = {c.id for c in checks if c.state == "pass"}
    playbook = get_playbooks()[task.field]
    return {
        "value": value or "",
        "label": playbook.label,
        "source_name": source.name if source else _("the source catalog"),
        "record_url": spec.record_url(value) if value else "",
        "search_url": spec.search_url(edition.get_isbn13() or ""),
        "match_rows": [{"label": r.label, "ours": r.ol_display, "theirs": r.target_display, "agrees": r.agrees} for r in rows],
        "checks": [{"id": c.id, "state": c.state, "tone": CHECK_TONES[c.state][0], "icon": CHECK_TONES[c.state][1], "message": c.message} for c in checks],
        "gate": identifiers.worst_state(checks),
        "traps": [{"text": t.text, "checked_by": t.checked_by, "checked": bool(t.checked_by and t.checked_by in caught)} for t in playbook.traps],
    }


def _task_context(edition, task: tasks.Task, names: dict[str, str]) -> dict:
    playbooks = get_playbooks()
    playbook = playbooks[task.field]
    others = _sibling_editions(edition)
    book = _book(edition)
    ev = task.evidence
    sources = get_sources()
    note = _prefilled_note(ev, sources, _sibling_top(task.field, others))
    ident = _identifier_context(edition, task, names) if identifiers.is_identifier_field(task.field) else None
    if ident:
        note = _prefilled_id_note(ident)
    return {
        "identifier": ident,
        "book": book,
        "task": {"key": task.key, "field": task.field, "mode": task.mode, "url": f"/contribute/task/{task.olid}/{task.field}"},
        "playbook": playbook,
        "question": playbook.question(task.mode),
        "evidence": _evidence_view(ev, sources),
        "siblings": _sibling_list(task.field, others),
        "sibling_total": len(others),
        "link_outs": link_outs(book["isbn13"], book["title"]),
        "note": note,
        "wait_days": load_scope().review_wait_days,
    }


def _prefilled_id_note(ident: dict) -> str:
    """The reviewer should not have to redo the lookup, so the receipt carries what was compared."""
    agreed = [r["label"] for r in ident["match_rows"] if r["agrees"] is True]
    if not agreed:
        return ""
    names = [str(a).lower() for a in agreed]
    joined = names[0] if len(names) == 1 else _("%(first)s and %(last)s", first=", ".join(names[:-1]), last=names[-1])
    return _("Checked against %(source)s: %(fields)s match.", source=ident["source_name"], fields=joined)


def _prefilled_note(ev, sources, sibling_top: str) -> str:
    names = [sources[v.source].name for v in ev.values if v.source in sources]
    if not names or not ev.suggestion_display:
        return ""
    parts = [_("Matched %(sources)s by ISBN.", sources=_(" and ").join(names))]
    if sibling_top and sibling_top == ev.suggestion_display:
        if ev.field == "languages":
            parts.append(_("Other editions of this work say the same."))
        else:
            parts.append(_("Other editions of this work use the same spelling."))
    return " ".join(parts)


class contribute_task(delegate.page):
    path = r"/contribute/task/(OL\d+M)/(languages|number_of_pages|publishers|subtitle|publish_date|lccn|oclc_numbers)"

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
    path = r"/contribute/task/(OL\d+M)/(languages|number_of_pages|publishers|subtitle|publish_date|lccn|oclc_numbers)/done"

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
