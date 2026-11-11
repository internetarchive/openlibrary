"""What the /tasks/admin pages show: every initiative with its status and progress, and one of them in detail.

Live figures come from the shared gaps, as on /tasks; people, saves and the trend come from the stats job's nightly
count docs, so they are a day behind and blank until the job has counted the initiative.
"""

from datetime import UTC, date, datetime, time, timedelta

from openlibrary.contribute import initiatives
from openlibrary.contribute.field_guides import get_field_guides
from openlibrary.core import admin
from openlibrary.core.helpers import commify, format_date
from openlibrary.i18n import gettext as _
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


def last_day(ends_at: datetime | None) -> date | None:
    """The last day a project runs. An end date is stored as the midnight after it, and a stop as the moment it happened."""
    return (ends_at - timedelta(microseconds=1)).date() if ends_at else None


def format_run(initiative: initiatives.Initiative) -> str:
    """When it runs, as one phrase. Dates are UTC days, as stored."""
    starts = format_day(initiative.starts_at)
    ends = format_day(datetime.combine(day, time())) if (day := last_day(initiative.ends_at)) else ""
    if not starts:
        return _("No start date")
    if not ends:
        return _("From %(start)s", start=starts)
    return _("%(start)s to %(end)s", start=starts, end=ends)


def latest_snapshot(docs: list[dict], slug: str) -> dict:
    """The stats job's newest counts for the initiative, or {} before it has any."""
    return next((counts[slug] for doc in reversed(docs) if slug in (counts := admin.initiative_counts(doc))), {})


def build_summary(initiative: initiatives.Initiative, docs: list[dict]) -> dict:
    """One initiative as the list shows it. Only a started one has gaps: asking for a draft's would pick its list early."""
    status = initiative.status()
    started = status in ("live", "ended")
    gaps = initiatives.get_gaps(initiative) if started else None
    progress = initiatives.progress(gaps, initiative.fields) if gaps is not None else None
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
        "people": format_count(latest_snapshot(docs, initiative.slug).get("people")),
    }


def build_index() -> dict:
    # A week back, so a night the stats job missed doesn't blank the people column.
    docs = admin.get_count_docs(7)
    projects = [build_summary(i, docs) for i in initiatives.every()]
    # A stable sort, so within a status the registry's order holds.
    return {"projects": sorted(projects, key=lambda p: STATUS_ORDER.index(p["status"]))}


def build_field_rows(initiative: initiatives.Initiative, gaps: list[list]) -> list[dict]:
    """Per field the initiative asks about: books still missing it, books where nobody could find it, and the rest."""
    guides = get_field_guides()
    rows = []
    for fld in initiative.fields:
        still_open = sum(1 for _key, _readers, open_fields, _skipped in gaps if fld in open_fields)
        not_found = sum(1 for _key, _readers, _open, skipped in gaps if fld in skipped)
        rows.append(
            {
                "label": guides[fld].label if fld in guides else fld,
                "open": commify(still_open),
                "not_found": commify(not_found),
                "filled": commify(len(gaps) - still_open - not_found),
                "percent": (len(gaps) - still_open) * 100 // len(gaps) if gaps else 0,
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
    gaps = initiatives.get_gaps(initiative) if started else None
    snapshot = latest_snapshot(docs, initiative.slug)
    picked = initiatives.started_at(initiative, site.get()) if started else None
    return {
        "project": summary,
        "index_url": BASE_URL,
        # The public page only lists it once it has started and while it isn't hidden.
        "public_url": f"/tasks?initiative={initiative.slug}" if started and not initiative.hidden else "",
        "picked": format_day(picked),
        "builtin": initiative.pick is not None,
        "not_found": format_count(summary["progress"]["not_found"]) if summary["progress"] else BLANK,
        "done": format_count(summary["progress"]["done"]) if summary["progress"] else BLANK,
        "people": format_count(snapshot.get("people")),
        "fields": build_field_rows(initiative, gaps) if gaps is not None else [],
        "trend": build_trend(docs, initiative.slug),
        "saves": build_saves(docs, initiative.slug),
    } | build_controls(initiative, summary["status"], initiatives.definition_doc(site.get(), initiative.slug))


TITLE_MAX = 80
DESCRIPTION_MAX = 300


def build_controls(initiative: initiatives.Initiative, status: str, doc: dict) -> dict:
    """What the project page's forms need: which actions apply now, the edit form's values, and the change log."""
    base = f"{BASE_URL}/{initiative.slug}"
    return {
        # Every form posts this back, so a change made against an out-of-date page is refused.
        "rev": doc.get("_rev", ""),
        "urls": {name: f"{base}/{name}" for name in ("edit", "hide", "unhide", "stop", "headline")},
        "can_hide": not initiative.hidden,
        "can_stop": status == "live",
        # Only a project the public can open can be the one /tasks opens on.
        "can_headline": status == "live" and not initiative.hidden and not initiative.featured,
        "form": {
            "title": initiative.title,
            "description": initiative.description if initiative.title else "",
            "starts": initiative.starts_at.date().isoformat() if initiative.starts_at else "",
            "ends": day.isoformat() if (day := last_day(initiative.ends_at)) else "",
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
    if not title and not initiative.pick:
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
    if end_day != last_day(initiative.ends_at):
        changes["ends_at"] = midnight(end_day + timedelta(days=1)) if end_day else None
    return changes, ""
