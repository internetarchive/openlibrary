"""Open Library Tasks at /tasks: books missing a field, and one page to fill each.

Answers save straight to the record as normal edits, so they show in its history and revert like any other.
"""

import random
from collections import Counter
from urllib.parse import urlencode

import web

from infogami.utils import delegate
from infogami.utils.view import query_param, render_template
from openlibrary import accounts
from openlibrary.contribute import save, supply, tasks
from openlibrary.contribute.field_guides import build_link_outs, get_field_guides
from openlibrary.contribute.tasks import field_values
from openlibrary.core import helpers
from openlibrary.i18n import gettext as _

LIST_SIZE = 50


def setup():
    pass


def get_filters() -> dict[str, tuple[str, tuple[str, ...]]]:
    """The rail's filters by ``task`` query value: a label and the fields it covers. Each must be filterable in Solr."""
    return {
        "languages": (_("Language"), ("languages",)),
        "publishers": (_("Publisher"), ("publishers",)),
        "identifiers": (_("Identifiers"), ("lccn", "oclc_numbers")),
    }


def normalize_filter(raw: str) -> str:
    return raw if raw in get_filters() else ""


def render_contribute(template: str, title: str, **params):
    return render_template("contribute", web.storage(template=template, title=title, params=params))


def require_librarian_access(path: str):
    """Login for visitors, permission denied for anyone below librarian. None when the user may continue."""
    user = accounts.get_current_user()
    if not user:
        raise web.seeother(f"/account/login?{urlencode({'redirect': path})}")
    if not user.is_librarian_or_higher():
        return render_template("permission_denied", path, _("Tasks are open to librarians only, for now"))
    return None


def build_dashboard_url(task: str = "", base: str = "/tasks") -> str:
    return f"{base}?{urlencode({'task': task})}" if task else base


def build_next_url(back: str, after: tasks.Task, saved: bool) -> str:
    """Another random task from the same filter, skipping the book just done; ``saved`` carries the receipt along."""
    params = {"task": back, "exclude": after.olid} | ({"saved": after.key} if saved else {})
    return f"/tasks/one?{urlencode({k: v for k, v in params.items() if v})}"


def get_language_names(codes: set[str]) -> dict[str, str]:
    names = {}
    for code in codes:
        if lang := web.ctx.site.get(f"/languages/{code}"):
            names[code] = lang.name or code
    return names


def build_sibling_rows(fld: str, others: list, limit: int = 10) -> list[dict]:
    """One line per other edition: its value for this field, plus enough to tell the editions apart. Filled ones first."""
    values = {e.key: field_values(e, fld) for e in others}
    names = get_language_names({str(v) for vs in values.values() for v in vs}) if fld == "languages" else {}
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


def format_field_value(edition, fld: str) -> str:
    """The field's current value as the receipt shows it."""
    values = field_values(edition, fld)
    if fld == "languages":
        names = get_language_names({str(v) for v in values})
        return ", ".join(names.get(str(v), str(v)) for v in values)
    return ", ".join(str(v) for v in values)


def build_edition_field_rows(edition, fld: str) -> list[dict]:
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
        value = (edition.get_isbn13() or ", ".join(edition.get("isbn_10") or [])) if f == "isbn" else format_field_value(edition, f)
        if value or f == fld:
            out.append({"label": label, "value": value, "ask": f == fld})
    return out


def count_sibling_values(fld: str, others: list, limit: int = 5) -> dict:
    """How often each value appears across the other editions, most common first."""
    values = [field_values(e, fld) for e in others]
    counts = Counter(str(v) for vs in values for v in vs)
    names = get_language_names(set(counts)) if fld == "languages" else {}
    total = len(others) or 1
    common = counts.most_common()
    return {
        "values": [{"value": v, "label": names.get(v, v), "count": n, "share": round(100 * n / total)} for v, n in common[:limit]],
        "more": len(common) - limit if len(common) > limit else 0,
        "unfilled": sum(1 for vs in values if not vs),
    }


def get_recent_fixes(user) -> list[dict]:
    """The right column's "Your recent fixes"."""
    changes = save.recent_saves(user.key)
    keys = [c.changes[0]["key"] for c in changes if c.changes]
    editions = {e.key: e for e in web.ctx.site.get_many(keys)} if keys else {}
    field_guides = get_field_guides()
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
                "field_label": field_guides[fld].label if fld in field_guides else "",
                "when": helpers.datestr(c.timestamp),
            }
        )
    return out


def build_book_header(edition, readers: int | None = None) -> dict:
    """What the book header shows. Live from the local record."""
    work = edition.works[0] if edition.works else None
    year = edition.get_publish_year()
    edition_line_parts = [p for p in [", ".join(edition.get("publishers") or []), str(year) if year else "", edition.get("physical_format") or ""] if p]
    seen: set[str] = set()
    author_names = []
    for a in edition.get_authors():
        if a and a.get("name") and a.key not in seen:
            seen.add(a.key)
            author_names.append(a.name)
    return {
        "key": edition.key,
        "olid": edition.key.split("/")[-1],
        "edit_url": edition.url(suffix="/edit"),
        "title": edition.get_title(),
        "authors": ", ".join(author_names),
        "cover_url": edition.get_cover_url("M"),
        "edition_line": " · ".join(edition_line_parts),
        "isbn13": edition.get_isbn13(),
        "edition_count": work.get_edition_count() if work else 1,
        "work_key": work.key if work else None,
        "readers": readers,
    }


def build_task_url(task: tasks.Task, back: str = "") -> str:
    url = f"/tasks/task/{task.olid}/{task.field}"
    return f"{url}?{urlencode({'back': back})}" if back else url


def build_task_summary(task: tasks.Task, field_guides, back: str = "") -> dict:
    field_guide = field_guides[task.field]
    return {
        "key": task.key,
        "field": task.field,
        "label": field_guide.label,
        "action_label": field_guide.action,
        "url": build_task_url(task, back),
    }


def build_task_rows(task: str) -> list[dict]:
    """The filter's books, most-read first, each with its open tasks weighted by ``tasks.impact`` for "Surprise me"."""
    fields = get_filters()[task][1] if task else tuple(tasks.POINTS)
    field_guides = get_field_guides()
    rows: list[dict] = []
    for cand in supply.solr_candidates(fields):
        if len(rows) == LIST_SIZE:
            break
        # Solr can lag the database; a field filled since the last reindex is no longer a task.
        if ts := [t for t in tasks.tasks_for_edition(cand.edition) if t.field in fields]:
            rows.append(
                {
                    "book": build_book_header(cand.edition, cand.readers),
                    "tasks": [build_task_summary(t, field_guides, task) | {"weight": tasks.impact(cand.readers, t)} for t in ts],
                }
            )
    return rows


def build_filter_rail(task: str) -> dict:
    filters = [
        {
            "label": label,
            "url": build_dashboard_url("" if task == fid else fid),
            "on": task == fid,
        }
        for fid, (label, _fields) in get_filters().items()
    ]
    return {"all": {"label": _("All open tasks"), "url": build_dashboard_url(), "on": not task}, "filters": filters}


class contribute_index(delegate.page):
    path = "/tasks"

    def GET(self):
        task = normalize_filter(query_param("task", ""))
        if denied := require_librarian_access(build_dashboard_url(task)):
            return denied
        user = accounts.get_current_user()
        return render_contribute(
            "contribute/dashboard.html.jinja",
            _("Tasks"),
            one_task_url=build_dashboard_url(task, base="/tasks/one"),
            rail=build_filter_rail(task),
            rows=build_task_rows(task),
            heading=_("Missing: %(field)s", field=get_filters()[task][0]) if task else _("Most needed"),
            empty=_("Nothing missing here right now. Thank you."),
            recent=get_recent_fixes(user),
            history_url=user.key,
        )


class contribute_one(delegate.page):
    """Do one task: a weighted random pick from the dashboard's current filter, straight to its task page."""

    path = "/tasks/one"

    def GET(self):
        task = normalize_filter(query_param("task", ""))
        if denied := require_librarian_access(build_dashboard_url(task, base=self.path)):
            return denied
        exclude = f"/books/{query_param('exclude', '')}"
        options = [t for row in build_task_rows(task) if row["book"]["key"] != exclude for t in row["tasks"]]
        if not options:
            raise web.seeother(build_dashboard_url(task))
        pick = random.choices(options, weights=[max(t["weight"], 1) for t in options])[0]
        saved = query_param("saved", "")
        raise web.seeother(f"{pick['url']}{'&' if '?' in pick['url'] else '?'}{urlencode({'saved': saved})}" if saved else pick["url"])


def get_sibling_editions(edition) -> list:
    work = edition.works[0] if edition.works else None
    if not work:
        return []
    return [e for e in work.get_sorted_editions(keys=[edition.key]) if e.key != edition.key]


def build_task_context(edition, task: tasks.Task, back: str, error: str = "", value: str = "", note: str = "") -> dict:
    field_guide = get_field_guides()[task.field]
    others = get_sibling_editions(edition) if field_guide.show_siblings else []
    siblings = build_sibling_rows(task.field, others)
    tally = count_sibling_values(task.field, others)
    book = build_book_header(edition)
    return {
        "book": book,
        "task": {
            "key": task.key,
            "field": task.field,
            "url": build_task_url(task, back),
            "skip_url": build_next_url(back, task, saved=False),
        },
        "is_identifier": task.field in save.NORMALIZERS,
        "field_guide": field_guide,
        "link_outs": build_link_outs(field_guide, book["isbn13"]),
        # Nothing to compare against when no other edition has a value.
        "siblings": siblings if any(s["value"] for s in siblings) else [],
        "sibling_total": len(others),
        "tally": tally,
        # Quick picks for the answer, only where the other editions are good evidence for this one.
        "suggestions": tally["values"][:3] if field_guide.suggest_from_siblings else [],
        "record_fields": build_edition_field_rows(edition, task.field),
        "list_url": build_dashboard_url(back),
        "next_scope": get_filters()[back][0] if back else "",
        "languages": save.language_options() if task.field == "languages" else [],
        "error": error,
        "value": value,
        "note": note,
    }


TASK_PATH = rf"/tasks/task/(OL\d+M)/({'|'.join(tasks.POINTS)})"


def get_back_filter() -> str:
    return normalize_filter(query_param("back", ""))


def build_receipt(saved: str) -> dict | None:
    """The previous task's "Saved" line, from a ``OL…M/field`` key, when "Save and next" brought us here."""
    olid, _sep, fld = saved.partition("/")
    field_guide = get_field_guides().get(fld)
    if not field_guide or not (edition := web.ctx.site.get(f"/books/{olid}")):
        return None
    return {"field_label": field_guide.label, "title": edition.title, "value": format_field_value(edition, fld), "url": edition.url()}


def get_edition_or_404(olid: str):
    edition = web.ctx.site.get(f"/books/{olid}")
    if not edition or edition.type.key != "/type/edition":
        raise web.notfound()
    return edition


def render_nothing_page(edition, fld: str, back: str):
    label = get_field_guides()[fld].label
    return render_contribute(
        "contribute/nothing.html.jinja", _("Nothing to fill in here"), book=build_book_header(edition), field_label=label, list_url=build_dashboard_url(back)
    )


class contribute_task(delegate.page):
    path = TASK_PATH

    def GET(self, olid, fld):
        if denied := require_librarian_access(f"/tasks/task/{olid}/{fld}"):
            return denied
        back = get_back_filter()
        edition = get_edition_or_404(olid)
        if not (task := tasks.task_for(edition, fld)):
            return render_nothing_page(edition, fld, back)
        context = build_task_context(edition, task, back) | {"receipt": build_receipt(query_param("saved", ""))}
        return render_contribute("contribute/task.html.jinja", get_field_guides()[fld].question, **context)

    def POST(self, olid, fld):
        if denied := require_librarian_access(f"/tasks/task/{olid}/{fld}"):
            return denied
        i = web.input(value="", note="", back="", confirmed="", then="")
        back = normalize_filter(i.back)
        edition = get_edition_or_404(olid)
        if not (task := tasks.task_for(edition, fld)):
            return render_nothing_page(edition, fld, back)
        done = f"/tasks/task/{olid}/{fld}/done"
        field_guide = get_field_guides()[fld]
        try:
            if fld in save.NORMALIZERS and not i.confirmed:
                raise save.InvalidAnswer(_("Open the record and confirm it matches this edition first."))
            save.save_answer(edition, fld, i.value, field_guide.label, i.note)
        except save.InvalidAnswer as e:
            context = build_task_context(edition, task, back, error=str(e), value=i.value, note=i.note)
            return render_contribute("contribute/task.html.jinja", field_guide.question, **context)
        if i.then == "next":
            raise web.seeother(build_next_url(back, task, saved=True))
        raise web.seeother(f"{done}?{urlencode({'choice': 'saved', 'back': back})}")


class contribute_done(delegate.page):
    path = TASK_PATH + "/done"

    def GET(self, olid, fld):
        if denied := require_librarian_access(f"/tasks/task/{olid}/{fld}/done"):
            return denied
        back = get_back_filter()
        edition = get_edition_or_404(olid)
        field_guides = get_field_guides()
        saved = query_param("choice", "") == "saved"
        same_book = [build_task_summary(t, field_guides, back) for t in tasks.tasks_for_edition(edition) if t.field != fld]
        return render_contribute(
            "contribute/done.html.jinja",
            _("Saved") if saved else _("Skipped"),
            book=build_book_header(edition),
            field_label=field_guides[fld].label,
            saved=saved,
            value=format_field_value(edition, fld) if saved else "",
            history_url=f"{edition.key}?m=history",
            same_book=same_book,
            next_url=build_next_url(back, tasks.Task(olid, fld), saved=False),
            list_url=build_dashboard_url(back),
        )
