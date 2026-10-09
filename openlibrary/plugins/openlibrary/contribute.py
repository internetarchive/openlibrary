"""The librarian dashboard at /contribute: books missing a field, and one page to fill it.

Three separable parts, kept in three places:

- **Supply**: the most-read works with an edition missing a field, from Solr.
  ``first_edits.supply``.
- **Tasks**: one empty field on one edition. ``first_edits.tasks``.
- **The task page**: the context to fill it in. Open Library fetches nothing
  from outside catalogs; the page links to them per the field's playbook and
  shows how the work's other editions fill the field.

An answer is saved straight to the record as a normal edit (``first_edits.save``),
so it shows in the record's history and can be reverted like any other.
Every page is for librarians.
"""

import random
from collections import Counter
from dataclasses import dataclass, field
from urllib.parse import urlencode

import web

from infogami.utils import delegate
from infogami.utils.view import query_param, render_template
from openlibrary import accounts
from openlibrary.core import helpers
from openlibrary.first_edits import identifiers, ranking, save, supply, tasks
from openlibrary.first_edits.playbooks import get_playbooks, link_outs
from openlibrary.first_edits.scope import load_scope
from openlibrary.first_edits.siblings import edition_field_values
from openlibrary.i18n import gettext as _

DENIED = "The contribute dashboard is for librarians"

# The Jinja page for each handler. Listed in full so template usage is greppable.
PAGES = {
    "dashboard": "contribute/dashboard.html.jinja",
    "task": "contribute/task.html.jinja",
    "nothing": "contribute/nothing.html.jinja",
    "done": "contribute/done.html.jinja",
}

LIST_SIZE = 50


def _task_filters() -> tuple:
    """The rail's filters: the ``task`` query value, its label, and the fields it covers. Each must be filterable in Solr."""
    return (
        ("languages", _("Language"), ("languages",)),
        ("publishers", _("Publisher"), ("publishers",)),
        ("identifiers", _("Identifiers"), ("lccn", "oclc_numbers")),
    )


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
    """Librarians and up: answers are saved straight to the record."""
    return bool(user and user.is_librarian_or_higher())


def _denied(path: str):
    return render_template("permission_denied", path, DENIED)


def _gate(path: str):
    """Login for visitors, permission denied for everyone else who isn't a librarian. None when the user may continue."""
    user = _user()
    if not user:
        raise web.seeother(f"/account/login?{urlencode({'redirect': path})}")
    if not _allowed(user):
        return _denied(path)
    return None


def _enabled_fields() -> tuple[str, ...]:
    return tuple(load_scope().enabled_fields())


def _filters() -> list[tuple]:
    """The rail filters whose fields are switched on in the scope."""
    enabled = set(_enabled_fields())
    return [(fid, label, tuple(f for f in fields if f in enabled)) for fid, label, fields in _task_filters() if enabled.intersection(fields)]


def _task_filter(raw: str) -> str:
    return raw if any(raw == fid for fid, _label, _fields in _filters()) else ""


def _filter_fields(task: str) -> tuple[str, ...]:
    """The fields a filter covers; no filter means every enabled field."""
    return next((fields for fid, _label, fields in _filters() if fid == task), _enabled_fields())


def _dashboard_url(task: str = "", base: str = "/contribute") -> str:
    return f"{base}?{urlencode({'task': task})}" if task else base


def _language_names(codes: set[str]) -> dict[str, str]:
    names = {}
    for code in codes:
        if lang := web.ctx.site.get(f"/languages/{code}"):
            names[code] = lang.name or code
    return names


def _sibling_list(fld: str, others: list, limit: int = 10) -> list[dict]:
    """One line per other edition: its value for this field, plus enough to tell the editions apart. Filled ones first."""
    values = {e.key: edition_field_values(e, fld) for e in others}
    names = _language_names({str(v) for vs in values.values() for v in vs}) if fld == "languages" else {}
    rows = []
    for e in sorted(others, key=lambda e: not values[e.key])[:limit]:
        year = e.get_publish_year()
        about = [
            ", ".join(e.get("publishers") or []) if fld != "publishers" else "",
            str(year) if year else "",
            e.get("physical_format") or "",
        ]
        rows.append({"url": e.key, "value": ", ".join(names.get(str(v), str(v)) for v in values[e.key]), "about": ", ".join(p for p in about if p)})
    return rows


def _display(edition, fld: str) -> str:
    """The field's current value as the receipt shows it."""
    values = edition_field_values(edition, fld)
    if fld == "languages":
        names = _language_names({str(v) for v in values})
        return ", ".join(names.get(str(v), str(v)) for v in values)
    return ", ".join(str(v) for v in values)


def _record(edition, fld: str) -> list[dict]:
    """The edition's record as the task page shows it: the fields it has, plus the one being asked about, in place."""
    rows = [
        ("publishers", _("Publisher")),
        ("publish_date", _("Published")),
        ("physical_format", _("Format")),
        ("number_of_pages", _("Pages")),
        ("languages", _("Language")),
        ("isbn", _("ISBN")),
        ("lccn", _("LCCN")),
        ("oclc_numbers", _("OCLC")),
    ]
    out = []
    for f, label in rows:
        value = (edition.get_isbn13() or ", ".join(edition.get("isbn_10") or [])) if f == "isbn" else _display(edition, f)
        if value or f == fld:
            out.append({"label": label, "value": value, "ask": f == fld})
    return out


def _tally(fld: str, others: list, limit: int = 5) -> dict:
    """How often each value appears across the other editions, most common first."""
    values = [edition_field_values(e, fld) for e in others]
    counts = Counter(str(v) for vs in values for v in vs)
    names = _language_names(set(counts)) if fld == "languages" else {}
    total = len(others) or 1
    common = counts.most_common()
    return {
        "values": [{"value": v, "label": names.get(v, v), "count": n, "share": round(100 * n / total)} for v, n in common[:limit]],
        "more": len(common) - limit if len(common) > limit else 0,
        "unfilled": sum(1 for vs in values if not vs),
    }


def _recent(user) -> list[dict]:
    """The right column's "Your recent fixes"."""
    changes = save.recent_saves(user.key)
    keys = [c.changes[0]["key"] for c in changes if c.changes]
    editions = {e.key: e for e in web.ctx.site.get_many(keys)} if keys else {}
    playbooks = get_playbooks()
    out = []
    for c in changes:
        key = c.changes[0]["key"] if c.changes else ""
        if not (edition := editions.get(key)):
            continue
        fld = (c.data or {}).get("field", "")
        out.append(
            {
                "title": edition.get_title(),
                "url": f"{key}?m=history",
                "field_label": playbooks[fld].label if fld in playbooks else "",
                "value": _display(edition, fld) if fld else "",
                "when": helpers.datestr(c.timestamp),
            }
        )
    return out


def _book(edition, readers: int | None = None) -> dict:
    """What the book header shows. Live from the local record."""
    work = edition.works[0] if edition.works else None
    year = edition.get_publish_year()
    parts = [p for p in [", ".join(edition.get("publishers") or []), str(year) if year else "", edition.get("physical_format") or ""] if p]
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
        "cover_url": edition.get_cover_url("M"),
        "edition_line": " · ".join(parts),
        "isbn13": edition.get_isbn13(),
        "edition_count": work.get_edition_count() if work else 1,
        "work_key": work.key if work else None,
        "readers": readers,
    }


def _task_url(task: tasks.Task, back: str = "") -> str:
    url = f"/contribute/task/{task.olid}/{task.field}"
    return f"{url}?{urlencode({'back': back})}" if back else url


def _task_summary(task: tasks.Task, playbooks, back: str = "") -> dict:
    playbook = playbooks[task.field]
    return {
        "key": task.key,
        "field": task.field,
        "label": playbook.label,
        "action_label": playbook.action,
        "question": playbook.question,
        "url": _task_url(task, back),
    }


def _rows(task: str) -> list[dict]:
    """The filter's books, most-read first, each with its open tasks narrowed to the filter's fields.

    Each task carries a ``weight`` (readers times the field's points) so "Surprise me" favors the fixes that help most.
    """
    fields = _filter_fields(task)
    playbooks = get_playbooks()
    scope = load_scope()
    rows = []
    for cand in supply.solr_candidates(fields, LIST_SIZE):
        # Solr can lag the database; a field filled since the last reindex is no longer a task.
        if ts := [t for t in tasks.tasks_for_edition(cand.edition, scope) if t.field in fields]:
            rows.append(
                {
                    "book": _book(cand.edition, cand.readers),
                    "tasks": [_task_summary(t, playbooks, task) | {"weight": ranking.impact(cand.readers, t, scope)} for t in ts],
                }
            )
    return rows


def _rail(task: str) -> dict:
    filters = [
        {
            "label": label,
            "url": _dashboard_url("" if task == fid else fid),
            "on": task == fid,
            "count": supply.missing_count(fields),
        }
        for fid, label, fields in _filters()
    ]
    return {"all": {"label": _("All open tasks"), "url": _dashboard_url(), "on": not task}, "filters": filters}


class contribute_index(delegate.page):
    path = "/contribute"

    def GET(self):
        task = _task_filter(query_param("task", ""))
        if denied := _gate(_dashboard_url(task)):
            return denied
        heading = next((label for fid, label, _fields in _filters() if fid == task), None)
        return _render(
            "dashboard",
            _("Contribute"),
            one_task_url=_dashboard_url(task, base="/contribute/one"),
            rail=_rail(task),
            rows=_rows(task),
            heading=_("Missing: %(field)s", field=heading) if heading else _("Most needed"),
            sort_note=_("Books more people read come first."),
            empty=_("Nothing missing here right now. Thank you."),
            recent=_recent(_user()),
        )


class contribute_one(delegate.page):
    """Do one task: a weighted random pick from the dashboard's current filter, straight to its task page."""

    path = "/contribute/one"

    def GET(self):
        task = _task_filter(query_param("task", ""))
        if denied := _gate(_dashboard_url(task, base=self.path)):
            return denied
        options = [t for row in _rows(task) for t in row["tasks"]]
        if not options:
            raise web.seeother(_dashboard_url(task))
        pick = random.choices(options, weights=[max(t["weight"], 1) for t in options])[0]
        raise web.seeother(pick["url"])


class contribute_redirect(delegate.page):
    """Old entry points, now the dashboard."""

    path = "/contribute/(start|needed|yours)"

    def GET(self, _old):
        raise web.seeother("/contribute")


def _sibling_editions(edition) -> list:
    work = edition.works[0] if edition.works else None
    if not work:
        return []
    return [e for e in work.get_sorted_editions(keys=[edition.key]) if e.key != edition.key]


def _task_context(edition, task: tasks.Task, back: str, error: str = "", value: str = "", note: str = "") -> dict:
    playbook = get_playbooks()[task.field]
    others = _sibling_editions(edition) if playbook.show_siblings else []
    siblings = _sibling_list(task.field, others)
    tally = _tally(task.field, others)
    book = _book(edition)
    return {
        "book": book,
        "task": {
            "key": task.key,
            "field": task.field,
            "url": _task_url(task, back),
            "skip_url": f"/contribute/task/{task.olid}/{task.field}/done?{urlencode({'choice': 'skipped', 'back': back})}",
        },
        "is_identifier": identifiers.is_identifier_field(task.field),
        "playbook": playbook,
        "link_outs": link_outs(playbook, book["isbn13"]),
        # Nothing to compare against when no other edition has a value.
        "siblings": siblings if any(s["value"] for s in siblings) else [],
        "sibling_total": len(others),
        "tally": tally,
        # Quick picks for the answer, only where the other editions are good evidence for this one.
        "suggestions": tally["values"][:3] if playbook.suggest_from_siblings else [],
        "record": _record(edition, task.field),
        "list_url": _dashboard_url(back),
        "languages": save.language_options() if task.field == "languages" else [],
        "error": error,
        "value": value,
        "note": note,
    }


TASK_PATH = r"/contribute/task/(OL\d+M)/(languages|number_of_pages|publishers|lccn|oclc_numbers)"


def _back() -> str:
    return _task_filter(query_param("back", ""))


def _edition_or_404(olid: str):
    edition = web.ctx.site.get(f"/books/{olid}")
    if not edition or edition.type.key != "/type/edition":
        raise web.notfound()
    return edition


def _nothing(edition, fld: str, back: str):
    label = get_playbooks()[fld].label
    return _render("nothing", _("Nothing to fill in here"), book=_book(edition), field_label=label, list_url=_dashboard_url(back))


class contribute_task(delegate.page):
    path = TASK_PATH

    def GET(self, olid, fld):
        if denied := _gate(f"/contribute/task/{olid}/{fld}"):
            return denied
        back = _back()
        edition = _edition_or_404(olid)
        if not (task := tasks.task_for(edition, fld)):
            return _nothing(edition, fld, back)
        return _render("task", get_playbooks()[fld].question, **_task_context(edition, task, back))

    def POST(self, olid, fld):
        if denied := _gate(f"/contribute/task/{olid}/{fld}"):
            return denied
        i = web.input(value="", note="", back="", confirmed="")
        back = _task_filter(i.back)
        edition = _edition_or_404(olid)
        if not (task := tasks.task_for(edition, fld)):
            return _nothing(edition, fld, back)
        done = f"/contribute/task/{olid}/{fld}/done"
        playbook = get_playbooks()[fld]
        try:
            if identifiers.is_identifier_field(fld) and not i.confirmed:
                raise save.InvalidAnswer(_("Open the record and confirm it matches this edition first."))
            save.save_answer(edition, fld, i.value, playbook.label, i.note)
        except save.InvalidAnswer as e:
            context = _task_context(edition, task, back, error=str(e), value=i.value, note=i.note)
            return _render("task", playbook.question, **context)
        raise web.seeother(f"{done}?{urlencode({'choice': 'saved', 'back': back})}")


class contribute_done(delegate.page):
    path = TASK_PATH + "/done"

    def GET(self, olid, fld):
        if denied := _gate(f"/contribute/task/{olid}/{fld}/done"):
            return denied
        back = _back()
        edition = _edition_or_404(olid)
        playbooks = get_playbooks()
        saved = query_param("choice", "") == "saved"
        same_book = [_task_summary(t, playbooks, back) for t in tasks.tasks_for_edition(edition) if t.field != fld]
        return _render(
            "done",
            _("Saved") if saved else _("Skipped"),
            book=_book(edition),
            field_label=playbooks[fld].label,
            saved=saved,
            value=_display(edition, fld) if saved else "",
            history_url=f"{edition.key}?m=history",
            same_book=same_book,
            task_key=f"{olid}/{fld}",
            list_url=_dashboard_url(back),
        )
