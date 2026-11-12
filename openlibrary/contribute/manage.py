"""What the /tasks/admin pages show: every initiative with its status and progress, and one of them in detail.

Live figures come from the shared gaps, as on /tasks; people, saves and the trend come from the stats job's nightly
count docs, so they are a day behind and blank until the job has counted the initiative.
"""

from datetime import UTC, date, datetime, time, timedelta

from openlibrary.contribute import booklist, initiatives, tasks
from openlibrary.contribute.field_guides import get_field_guides
from openlibrary.core import admin
from openlibrary.core.helpers import commify, format_date
from openlibrary.i18n import gettext as _
from openlibrary.i18n import ungettext
from openlibrary.utils.request_context import site

BASE_URL = "/tasks/admin"
# The list's order: what is running, then what is coming, then what is over.
STATUS_ORDER = ("live", "scheduled", "draft", "ended")
# Two 28-day windows, so the trend has something to compare.
TREND_DAYS = 56
SAVES_DAYS = 28
BLANK = "—"


def status_labels() -> dict[str, str]:
    return {"live": _("Live"), "scheduled": _("Scheduled"), "draft": _("Draft"), "ended": _("Ended")}


def format_count(value: int | None) -> str:
    return BLANK if value is None else commify(value)


def format_day(when: datetime | None) -> str:
    return format_date(when) if when else ""


def format_run(initiative: initiatives.Initiative) -> str:
    """When it runs, as one phrase. Dates are UTC days, as stored."""
    starts = format_day(initiative.starts_at)
    ends = format_day(datetime.combine(day, time())) if (day := initiatives.last_day(initiative.ends_at)) else ""
    if not starts:
        return _("No start date")
    if not ends:
        return _("From %(start)s", start=starts)
    return _("%(start)s to %(end)s", start=starts, end=ends)


def latest_snapshot(docs: list[dict], slug: str) -> dict:
    """The stats job's newest counts for the initiative, or {} before it has any."""
    return next((counts[slug] for doc in reversed(docs) if slug in (counts := admin.initiative_counts(doc))), {})


def build_summary(initiative: initiatives.Initiative, docs: list[dict]) -> dict:
    """One initiative as the list shows it.

    A built-in one has gaps only once it starts: asking sooner would pick its list early. One set up here is counted
    from the day it is made, which is how whoever made it checks the books before it starts.
    """
    status = initiative.status()
    started = status in ("live", "ended") or not initiatives.is_builtin(initiative)
    gaps = initiatives.get_gaps(initiative) if started else None
    progress = initiatives.progress(gaps, initiative.fields, initiative.start) if gaps is not None else None
    guides = get_field_guides()
    return initiatives.describe(initiative) | {
        "slug": initiative.slug,
        "url": f"{BASE_URL}/{initiative.slug}",
        "status": status,
        "status_label": status_labels()[status],
        "hidden": initiative.hidden,
        "featured": initiative.featured and status == "live",
        "run": format_run(initiative),
        "fields": [guides[f].label if f in guides else f for f in initiative.fields],
        "books": format_count(progress["total"] if progress else initiative.size or None),
        # Started, but the shared gaps aren't built yet; the page says so rather than showing zeros.
        "building": started and progress is None,
        "progress": progress,
        "tasks_left": format_count(progress["open"]) if progress else BLANK,
        # Closed since the start, out of what was open then; a gap emptied after the start can't push it below 0.
        "tasks_done": format_count(max(0, progress["start"] - progress["open"])) if progress else BLANK,
        "tasks_total": format_count(progress["start"]) if progress else "",
        "people": format_count(latest_snapshot(docs, initiative.slug).get("people")),
    }


def build_index() -> dict:
    # A week back, so a night the stats job missed doesn't blank the people column.
    docs = admin.get_count_docs(7)
    projects = [build_summary(i, docs) for i in initiatives.every()]
    # A stable sort, so within a status the registry's order holds.
    return {"projects": sorted(projects, key=lambda p: STATUS_ORDER.index(p["status"])), "new_url": f"{BASE_URL}/new"}


def build_field_rows(initiative: initiatives.Initiative, gaps: list[list]) -> list[dict]:
    """Per field the initiative asks about, against what was open at the start: filled since, nobody could find since,
    still open, and the books that already had it. Without a recorded start, today is the start."""
    guides = get_field_guides()
    starts = (initiative.start or {}).get("fields") or {}
    rows = []
    for fld in initiative.fields:
        counts = initiatives.field_counts(gaps, fld)
        total, still_open, not_found = counts["total"], counts["open"], counts["not_found"]
        began = starts.get(fld) or {"open": still_open, "not_found": not_found}
        unfound = max(0, not_found - began["not_found"])
        rows.append(
            {
                "label": guides[fld].label if fld in guides else fld,
                "open": commify(still_open),
                "not_found": commify(unfound),
                "filled": commify(max(0, began["open"] - still_open - unfound)),
                "percent": initiatives.closed_share(began["open"], still_open),
                # A work detail is counted once per work, an edition detail once per edition.
                "out_of": (
                    ungettext("%(count)s work", "%(count)s works", began["open"], count=commify(began["open"]))
                    if fld in tasks.WORK_FIELDS
                    else ungettext("%(count)s edition", "%(count)s editions", began["open"], count=commify(began["open"]))
                ),
                "had": commify(max(0, total - began["open"] - began["not_found"])),
            }
        )
    return rows


def sparkline_points(values: list[int | None], width: int = 100, height: int = 32) -> str:
    """SVG polyline points for a series, skipping days with no count. "" with fewer than two counts: one point is no trend."""
    known = [(i, v) for i, v in enumerate(values) if v is not None]
    if len(known) < 2:
        return ""
    low, high = min(v for _i, v in known), max(v for _i, v in known)
    span = (high - low) or 1
    last = len(values) - 1
    # A 2px margin top and bottom keeps the stroke inside the box.
    return " ".join(f"{i * width / last:.1f},{2 + (high - v) * (height - 4) / span:.1f}" for i, v in known)


def build_trend(docs: list[dict], slug: str) -> dict:
    """Details still open by day, for the sparkline, with the change across it."""
    values = [admin.initiative_counts(doc).get(slug, {}).get("open") for doc in docs]
    known = [v for v in values if v is not None]
    # From the first day it was counted, so a young project's line fills the chart instead of hugging its right edge.
    values = values[next((i for i, v in enumerate(values) if v is not None), 0) :]
    return {
        "points": sparkline_points(values),
        "first": format_count(known[0]) if known else BLANK,
        "last": format_count(known[-1]) if known else BLANK,
        "days": len(known),
    }


def build_saves(docs: list[dict], slug: str) -> dict:
    """Saves by day over the last ``SAVES_DAYS``, as bar heights, with the 28-day total and how many were since undone."""
    days = [{"day": doc["_key"][-10:], "count": (doc.get("tasks_saves_by_initiative_1d") or {}).get(slug)} for doc in docs[-SAVES_DAYS:]]
    counted = [d for d in days if d["count"] is not None]
    peak = max((d["count"] for d in counted), default=0)
    window = next((w[slug] for doc in reversed(docs) if slug in (w := doc.get("tasks_saves_by_initiative_28d") or {})), None)
    saves, undone = (window["saves"], window["undone"]) if window else (None, None)
    return {
        "bars": [{"day": d["day"], "count": commify(d["count"] or 0), "height": (d["count"] or 0) * 100 // peak if peak else 0} for d in days] if counted else [],
        "counted": saves is not None,
        "total": format_count(saves),
        "undone": format_count(undone),
        "undone_share": _("%(percent)s%%", percent=round(undone * 100 / saves)) if saves and undone is not None else "",
    }


def build_detail(initiative: initiatives.Initiative) -> dict:
    docs = admin.get_count_docs(TREND_DAYS)
    summary = build_summary(initiative, docs)
    started = summary["status"] in ("live", "ended")
    builtin = initiatives.is_builtin(initiative)
    gaps = initiatives.get_gaps(initiative) if started or not builtin else None
    snapshot = latest_snapshot(docs, initiative.slug)
    picked = initiatives.started_at(initiative, site.get()) if started or not builtin else None
    doc = initiatives.definition_doc(site.get(), initiative.slug)
    return {
        "project": summary,
        "index_url": BASE_URL,
        # The public page only lists it once it has started and while it isn't hidden.
        "public_url": f"/tasks?initiative={initiative.slug}" if started and not initiative.hidden else "",
        "picked": format_day(picked),
        "builtin": builtin,
        "skipped": build_skipped(doc.get("skipped") or [], doc.get("skipped_count") or 0),
        "not_found": format_count(summary["progress"]["not_found"]) if summary["progress"] else BLANK,
        "done": format_count(summary["progress"]["done"]) if summary["progress"] else BLANK,
        "people": format_count(snapshot.get("people")),
        "fields": build_field_rows(initiative, gaps) if gaps is not None else [],
        "trend": build_trend(docs, initiative.slug),
        "saves": build_saves(docs, initiative.slug),
    } | build_controls(initiative, summary["status"], doc)


TITLE_MAX = 80
DESCRIPTION_MAX = 300


def build_controls(initiative: initiatives.Initiative, status: str, doc: dict) -> dict:
    """What the project page's forms need: which actions apply now, the edit form's values, and the change log."""
    base = f"{BASE_URL}/{initiative.slug}"
    return {
        # Every form posts this back, so a change made against an out-of-date page is refused.
        "rev": doc.get("_rev", ""),
        "urls": {name: f"{base}/{name}" for name in ("edit", "hide", "unhide", "stop", "headline", "delete")},
        # Once it has started, people have saved toward it, so it can only be stopped or hidden.
        "can_delete": not initiatives.is_builtin(initiative) and status in ("draft", "scheduled"),
        "can_hide": not initiative.hidden,
        "can_stop": status == "live",
        # Only a project the public can open can be the one /tasks opens on.
        "can_headline": status == "live" and not initiative.hidden and not initiative.featured,
        "form": {
            "title": initiative.title,
            "description": initiative.description if initiative.title else "",
            "starts": initiative.starts_at.date().isoformat() if initiative.starts_at else "",
            "ends": day.isoformat() if (day := initiatives.last_day(initiative.ends_at)) else "",
            "title_max": TITLE_MAX,
            "description_max": DESCRIPTION_MAX,
        },
        "log": build_log(doc),
    }


def edit_labels() -> dict[str, str]:
    return {"title": _("title"), "description": _("description"), "starts_at": _("start date"), "ends_at": _("end date")}


def describe_change(entry: dict) -> str:
    """One log entry in words."""
    plain = {
        "create": _("Created the project"),
        "hide": _("Hid the project"),
        "unhide": _("Made the project visible again"),
        "stop": _("Stopped the project early"),
        "headline": _("Made it the headline project"),
        "unheadline": _("Another project became the headline"),
    }
    if (action := entry.get("action")) in plain:
        return plain[action]
    labels = edit_labels()
    return _("Edited: %(details)s", details=", ".join(labels[k] for k in entry.get("changes") or {} if k in labels))


def build_log(doc: dict) -> list[dict]:
    """The definition's change log, newest first."""
    return [
        {
            "when": _("%(time)s UTC", time=str(entry.get("at", ""))[:16].replace("T", " ")),
            "who": str(entry.get("by", "")).rsplit("/", maxsplit=1)[-1],
            "who_url": str(entry.get("by", "")),
            "what": describe_change(entry),
        }
        for entry in reversed(doc.get("log") or [])
    ]


def parse_day(raw: str) -> date | None:
    return date.fromisoformat(raw) if raw else None


def midnight(day: date) -> str:
    return datetime.combine(day, time(), tzinfo=UTC).isoformat(timespec="seconds")


def parse_edit(initiative: initiatives.Initiative, title: str, description: str, starts: str, ends: str) -> tuple[dict, str]:
    """The edit form as changes to the definition, or an error to show. Only what differs is a change, so the log says what moved.

    A built-in project may leave the title blank: it then keeps its own name and description, which are translated.
    """
    title, description = title.strip(), description.strip()
    try:
        start_day, end_day = parse_day(starts), parse_day(ends)
    except ValueError:
        return {}, _("That date isn't one we can read.")
    if not title and not initiatives.is_builtin(initiative):
        return {}, _("A project needs a title.")
    if len(title) > TITLE_MAX or len(description) > DESCRIPTION_MAX:
        return {}, _("The title or description is too long.")
    if end_day and not start_day:
        return {}, _("A project with an end date needs a start date.")
    if end_day and start_day and end_day < start_day:
        return {}, _("The end date is before the start date.")
    if not title:
        description = ""
    changes: dict = {}
    if title != initiative.title:
        changes["title"] = title
    if description != (initiative.description if initiative.title else ""):
        changes["description"] = description
    if start_day != (initiative.starts_at.date() if initiative.starts_at else None):
        changes["starts_at"] = midnight(start_day) if start_day else None
    # Compared as days: a project stopped at 2pm still shows that day, and saving the form again mustn't restart it until midnight.
    if end_day != initiatives.last_day(initiative.ends_at):
        changes["ends_at"] = midnight(end_day + timedelta(days=1)) if end_day else None
    return changes, ""


SOURCES = ("pasted", "list", "most-shelved", "most-shelved-missing")
SKIPPED_KEPT = 50
DEFAULT_SIZE = 500


def skip_reasons() -> dict[str, str]:
    return {
        "unknown": _("Not an Open Library ID or an ISBN"),
        "no_isbn": _("No book has this ISBN"),
        "missing": _("No such book"),
        "not_book": _("Not a book"),
        "no_edition": _("This work has no editions"),
        "duplicate": _("Listed twice"),
        "same_work": _("Another edition of the same work is already listed"),
        "over_limit": _("Past the limit of %(count)s books", count=commify(booklist.MAX_BOOKS)),
    }


def build_skipped(skipped: list[dict], count: int) -> dict:
    """What the book list left out when the project was made: the first few entries with why, and how many in all."""
    reasons = skip_reasons()
    return {
        "count": commify(count) if count else "",
        "rows": [{"entry": str(s.get("entry", "")), "reason": reasons.get(str(s.get("reason")), "")} for s in skipped],
        "more": count > len(skipped),
    }


def build_new_form(values: dict | None = None, error: str = "") -> dict:
    """The create form, blank or as it was posted with what was wrong."""
    guides = get_field_guides()
    values = values or {}
    chosen = set(values.get("fields") or ())
    return {
        "index_url": BASE_URL,
        "action": f"{BASE_URL}/new",
        "error": error,
        "form": dict.fromkeys(("title", "description", "books", "list_url", "starts", "ends"), "")
        | {"source": "pasted", "size": str(DEFAULT_SIZE)}
        | {k: v for k, v in values.items() if k != "fields" and v},
        "field_groups": [
            {
                "id": group,
                "legend": legend,
                "hint": hint,
                "fields": [
                    {"value": f, "label": guides[f].label if f in guides else f, "checked": f in chosen}
                    for f in tasks.POINTS
                    if (f in tasks.WORK_FIELDS) == (group == "work")
                ],
            }
            for group, legend, hint in (
                ("edition", _("About the edition"), _("One published version of a book. Asked of every edition in the project.")),
                ("work", _("About the work"), _("Shared by every edition of a book. Asked once per work, however many of its editions are in the project.")),
            )
        ],
        "title_max": TITLE_MAX,
        "description_max": DESCRIPTION_MAX,
        "max_books": commify(booklist.MAX_BOOKS),
    }


def parse_create(values: dict) -> tuple[dict, booklist.Resolved | None, str]:
    """The create form as a definition and, when the books were named, the list they resolve to; or an error to show.

    A picker's list is picked later, off the request, so there is nothing to resolve for one here.
    """
    title, description = str(values.get("title", "")).strip(), str(values.get("description", "")).strip()
    fields = [f for f in tasks.POINTS if f in (values.get("fields") or ())]
    source = values.get("source")
    if not title:
        return {}, None, _("A project needs a title.")
    if len(title) > TITLE_MAX or len(description) > DESCRIPTION_MAX:
        return {}, None, _("The title or description is too long.")
    if not fields:
        return {}, None, _("Choose at least one detail for the project to ask for.")
    if source not in SOURCES:
        return {}, None, _("Choose where the books come from.")
    try:
        start_day, end_day = parse_day(str(values.get("starts", ""))), parse_day(str(values.get("ends", "")))
    except ValueError:
        return {}, None, _("That date isn't one we can read.")
    if end_day and not start_day:
        return {}, None, _("A project with an end date needs a start date.")
    if end_day and start_day and end_day < start_day:
        return {}, None, _("The end date is before the start date.")
    definition: dict = {
        "title": title,
        "description": description,
        "fields": fields,
        "starts_at": midnight(start_day) if start_day else None,
        "ends_at": midnight(end_day + timedelta(days=1)) if end_day else None,
        "source": source,
    }
    if source in ("most-shelved", "most-shelved-missing"):
        size = str(values.get("size", "")).strip()
        if not (size.isascii() and size.isdigit() and 1 <= int(size) <= booklist.MAX_BOOKS):
            return {}, None, _("Choose how many books, from 1 to %(count)s.", count=commify(booklist.MAX_BOOKS))
        return definition | {"picker": source, "size": int(size)}, None, ""
    # With only work details to ask, a second edition of a work would add nothing to do.
    one_per_work = tasks.WORK_FIELDS.issuperset(fields)
    if source == "list":
        if (resolved := booklist.resolve_list(site.get(), str(values.get("list_url", "")), one_per_work)) is None:
            return {}, None, _("That isn't an Open Library list we can find.")
    else:
        resolved = booklist.resolve(site.get(), booklist.split_entries(str(values.get("books", ""))), one_per_work)
    if not resolved.picks:
        return {}, None, _("None of those are books the project can use.")
    definition |= {"size": len(resolved.picks), "skipped": resolved.skipped[:SKIPPED_KEPT], "skipped_count": len(resolved.skipped)}
    return definition, resolved, ""
