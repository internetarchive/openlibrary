"""Open Library Tasks at /tasks: books missing a field, and one page to fill each.

Answers save straight to the record as normal edits, so they show in its history and revert like any other.
"""

import random
from collections import Counter
from datetime import UTC, datetime
from urllib.parse import urlencode

import web

from infogami.utils import delegate
from infogami.utils.view import query_param, render_template
from openlibrary import accounts
from openlibrary.contribute import feed, initiatives, save, supply, tasks
from openlibrary.contribute.field_guides import AMAZON_COVER, build_link_outs, get_field_guides
from openlibrary.contribute.tasks import field_values, work_of
from openlibrary.core import helpers
from openlibrary.core.tags import can_edit_tags, find_tag, tag_choices, work_tag_keys
from openlibrary.i18n import gettext as _
from openlibrary.plugins.upstream import spamcheck
from openlibrary.plugins.upstream.utils import markdown_excerpt

LIST_SIZE = 25
# Placeholder cards while a cold cache builds the list in the background; the script swaps them for the rows.
LIST_SKELETON_ROWS = 4
# Rows the public page renders before the feed script takes over.
FEED_SIZE = 12
# Placeholder rows while a cold cache rebuilds the feed pool in the background; the script swaps them for rows as they arrive.
FEED_SKELETON_ROWS = 6
# The "Volunteering @ Open Library" form; applying is how a reader becomes an Open Librarian.
APPLY_FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLSeU5Y4x6LNl2SW4NktRnZhFUDwhV6l9Xzr-IsqBow1KqNfdYw/viewform"
# The form's "What is your Open Library username?" field, prefilled for signed-in visitors.
APPLY_FORM_USERNAME_FIELD = "entry.629295430"
# Signed-in members see the /tasks intro once. Clicking through sets this cookie, the way banner dismissals do.
INTRO_COOKIE = "tasks_intro"
INTRO_COOKIE_DAYS = 365


def setup():
    pass


def get_filters() -> dict[str, tuple[str, tuple[str, ...]]]:
    """The rail's filters by ``task`` query value: a label and the fields it covers."""
    return {
        "covers": (_("Cover"), ("covers",)),
        "languages": (_("Language"), ("languages",)),
        "number_of_pages": (_("Page count"), ("number_of_pages",)),
        "publishers": (_("Publisher"), ("publishers",)),
        "identifiers": (_("Identifiers"), ("lccn", "oclc_numbers")),
        "literary_form": (_("Fiction or nonfiction"), ("literary_form",)),
    }


def get_filter_headings() -> dict[str, str]:
    """The dashboard's heading per filter: a whole phrase, so each language can case and order it."""
    return {
        "covers": _("Missing cover"),
        "languages": _("Missing language"),
        "number_of_pages": _("Missing page count"),
        "publishers": _("Missing publisher"),
        "identifiers": _("Missing identifiers"),
        "literary_form": _("Missing fiction or nonfiction"),
    }


def fields_for(user) -> tuple[str, ...]:
    """The task fields this visitor sees: the beta ones only on the tags whitelist."""
    return tasks.visible_fields(can_edit_tags(user))


def visible_filters(fields: tuple[str, ...]) -> dict[str, tuple[str, tuple[str, ...]]]:
    return {fid: f for fid, f in get_filters().items() if set(f[1]) <= set(fields)}


def normalize_filter(raw: str, fields: tuple[str, ...] = tuple(tasks.POINTS)) -> str:
    return raw if raw in visible_filters(fields) else ""


def render_contribute(template: str, title: str, **params):
    return render_template("contribute", web.storage(template=template, title=title, params=params))


def require_login(path: str):
    """The signed-in user; visitors are sent to log in and brought back to ``path``."""
    if not (user := accounts.get_current_user()):
        raise web.seeother(f"/account/login?{urlencode({'redirect': path})}")
    return user


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
    """The field's current value as the receipt shows it. A cover is shown as the image instead."""
    if fld == "covers":
        return ""
    if fld in tasks.WORK_FIELDS:
        work = work_of(edition)
        return ", ".join(tag.name for k in (work_tag_keys(work, fld) if work else []) if (tag := find_tag(fld, k)))
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
        # Last, so the publisher, year and ISBN to check the images against are read first.
        ("covers", _("Cover")),
    ]
    out = []
    for f, label in rows:
        value = (edition.get_isbn13() or ", ".join(edition.get("isbn_10") or [])) if f == "isbn" else format_field_value(edition, f)
        if value or f == fld:
            out.append({"label": label, "value": value, "ask": f == fld})
    return out


def text_of(block) -> str:
    """A description's text, whether stored as a string or a ``/type/text`` block."""
    return str(getattr(block, "value", block) or "")


def build_work_field_rows(edition, fld: str) -> list[dict]:
    """The work's record as a work-level task shows it: what the whole work says, with the blank in place."""
    work = work_of(edition)
    subjects = (work.get("subjects") or [])[:8] if work else []
    rows = [
        (_("First published"), work.get("first_publish_date") if work else ""),
        (_("Subjects"), ", ".join(subjects)),
        (_("Editions"), str(edition.works[0].get_edition_count()) if edition.works else ""),
    ]
    out = [{"label": label, "value": value, "ask": False} for label, value in rows if value]
    out.append({"label": get_field_guides()[fld].label, "value": "", "ask": True})
    return out


# The choice-list row that is an honest exit rather than an answer.
UNSURE = "unsure"


def field_guide_choices(fld: str) -> str:
    return get_field_guides()[fld].choices


def build_choices(field_guide) -> list:
    """A choice field's rows: the tag type's tags, then "Not sure"."""
    if not field_guide.choices:
        return []
    return tag_choices(field_guide.choices, field_guide.not_found or _("Not sure"), unsure_value=UNSURE)


def build_evidence(edition) -> str:
    """What the record itself says, for a task that is a judgment rather than a lookup: the blurb, as plain text."""
    work = work_of(edition)
    blurb = (text_of(work.get("description")) if work else "") or text_of(edition.get("description"))
    return markdown_excerpt(blurb, max_length=600)


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


def get_recent_fixes(changes: list) -> list[dict]:
    """The right column's "Your recent fixes", from the user's ``save.recent_saves``."""
    keys = [c.changes[0]["key"] for c in changes if c.changes]
    # An edition for most fields; the work for a work field.
    records = {r.key: r for r in web.ctx.site.get_many(keys)} if keys else {}
    field_guides = get_field_guides()
    out = []
    for c in changes:
        key = c.changes[0]["key"] if c.changes else ""
        if not (record := records.get(key)):
            continue
        fld = (c.data or {}).get("field", "")
        out.append(
            {
                "title": record.get_title() if record.type.key == "/type/edition" else record.title,
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


def build_task_rows(task: str, visible: tuple[str, ...] = tuple(tasks.POINTS)) -> list[dict] | None:
    """A random draw of the filter's books from the active initiative, each with its open tasks weighted by ``tasks.impact`` for "Surprise me".

    ``visible`` is what this visitor may see; a filter narrows it further. None while the initiative's gaps are still being built.
    """
    fields = get_filters()[task][1] if task else visible
    if (candidates := supply.candidates(fields)) is None:
        return None
    field_guides = get_field_guides()
    rows: list[dict] = []
    for cand in candidates:
        if len(rows) == LIST_SIZE:
            break
        # The shared gaps can lag the database; a field filled since the last rebuild is no longer a task.
        if ts := [t for t in tasks.tasks_for_edition(cand.edition) if t.field in fields and t.field not in cand.not_found]:
            rows.append(
                {
                    "book": build_book_header(cand.edition, cand.readers),
                    "tasks": [build_task_summary(t, field_guides, task) | {"weight": tasks.impact(cand.readers, t)} for t in ts],
                }
            )
    return rows


def build_progress(fields: tuple[str, ...]) -> dict | None:
    """The active initiative's progress for the dashboard, or None while its gaps are still being built."""
    if not (gaps := initiatives.get_gaps()):
        return None
    p = initiatives.progress(gaps, fields)
    return {
        "title": _("The %(count)s most-read books", count=helpers.commify(p["total"])),
        "percent": p["percent"],
        "figure": _("%(percent)s%%", percent=p["percent"]),
        "description": _("Fill in what's missing on the books people shelve most."),
    }


def build_filter_rail(task: str, fields: tuple[str, ...]) -> dict:
    filters = [
        {
            "label": label,
            "url": build_dashboard_url("" if task == fid else fid),
            "on": task == fid,
            "track": fid,
        }
        for fid, (label, _fields) in visible_filters(fields).items()
    ]
    return {"all": {"label": _("All open tasks"), "url": build_dashboard_url(), "on": not task, "track": "all"}, "filters": filters}


def landing_figures() -> dict[str, str]:
    """Social proof on the public page, set as one sentence there. Hand-set round figures for now; revisit when a stats source exists."""
    return {"readers": "2M+", "books": "55M"}


def has_seen_intro(recent_saves: list) -> bool:
    """Whether a member skips the intro: they clicked through it before, or have already saved a task (any device)."""
    return web.cookies().get(INTRO_COOKIE) == "1" or bool(recent_saves)


def build_cta(user=None) -> dict:
    """The way in. A visitor needs a free account; a member goes straight to a task, and either click dismisses the intro."""
    if user:
        return {
            "heading": _("Ready when you are"),
            "label": _("Try a task"),
            "href": build_dashboard_url(base="/tasks/one"),
            "note": "",
            "secondary": [{"label": _("Browse all tasks"), "href": build_dashboard_url(), "track": "Browse"}],
            "intro": {"cookie": INTRO_COOKIE, "days": INTRO_COOKIE_DAYS},
        }
    return {
        "heading": _("Join in"),
        "label": _("Create an account"),
        "href": f"/account/create?{urlencode({'redirect': '/tasks'})}",
        "note": _("Tasks are open to anyone with a free Open Library account."),
        "secondary": [{"label": _("Already have one? Log in"), "href": f"/account/login?{urlencode({'redirect': '/tasks'})}", "track": "LogIn"}],
        "intro": None,
    }


def build_apply(user) -> dict | None:
    """The librarian pitch for members who aren't one yet. The form asks for a username, so it's prefilled."""
    if user.is_librarian_or_higher():
        return None
    return {
        "label": _("Become an Open Librarian"),
        "href": f"{APPLY_FORM_URL}?{urlencode({'usp': 'pp_url', APPLY_FORM_USERNAME_FIELD: user.get_username()})}",
        "note": _("Doing a lot of these? Open Librarians get more editing tools. Applying takes a few minutes."),
    }


def format_when(timestamp: str) -> str:
    """Relative time for a feed row's ISO timestamp; datestr compares naive datetimes."""
    then = datetime.fromisoformat(timestamp).astimezone(UTC).replace(tzinfo=None)
    return helpers.datestr(then, now=datetime.now(UTC).replace(tzinfo=None))


def build_feed() -> dict:
    """The feed's first rows plus what the script needs to keep it moving."""
    rows = feed.recent_rows(FEED_SIZE)
    for row in rows:
        row["when"] = format_when(row["timestamp"])
    return {
        "rows": rows,
        "url": "/tasks/feed.json",
        "cursor": str(len(rows)),
        "skeleton_rows": 0 if rows else FEED_SKELETON_ROWS,
    }


def render_landing(user=None):
    """The /tasks intro: what tasks are, who is doing them, how to join. Visitors always; members until they click through."""
    return render_contribute(
        "contribute/landing.html.jinja",
        _("Tasks"),
        cta=build_cta(user),
        figures=landing_figures(),
        feed=build_feed(),
        # A few appealing examples, not the full list.
        fields=[get_field_guides()[f].label for f in ("covers", "languages", "publishers", "oclc_numbers")],
    )


class contribute_index(delegate.page):
    path = "/tasks"

    def GET(self):
        if not (user := accounts.get_current_user()):
            return render_landing()
        # One query for both the intro check and the "recent fixes" column.
        recent_saves = save.recent_saves(user.key)
        if not has_seen_intro(recent_saves):
            return render_landing(user)
        fields = fields_for(user)
        task = normalize_filter(query_param("task", ""), fields)
        rows = build_task_rows(task, fields)
        return render_contribute(
            "contribute/dashboard.html.jinja",
            _("Tasks"),
            one_task_url=build_dashboard_url(task, base="/tasks/one"),
            rail=build_filter_rail(task, fields),
            rows=rows,
            # While the pool builds, the script fetches the rows from here.
            rows_url=build_dashboard_url(task, base="/tasks/rows") if rows is None else "",
            skeleton_rows=LIST_SKELETON_ROWS if rows is None else 0,
            heading=get_filter_headings()[task] if task else _("Most needed"),
            empty=_("Nothing missing here right now. Thank you."),
            recent=get_recent_fixes(recent_saves),
            history_url=user.key,
            apply=build_apply(user),
            progress=build_progress(fields),
        )


class contribute_one(delegate.page):
    """Do one task: a weighted random pick from the dashboard's current filter, straight to its task page.

    While the pool is still being built there is nothing to pick from, so this lands on the dashboard, which shows the wait.
    """

    path = "/tasks/one"

    def GET(self):
        user = require_login(build_dashboard_url(normalize_filter(query_param("task", "")), base=self.path))
        fields = fields_for(user)
        task = normalize_filter(query_param("task", ""), fields)
        exclude = f"/books/{query_param('exclude', '')}"
        options = [t for row in build_task_rows(task, fields) or [] if row["book"]["key"] != exclude for t in row["tasks"]]
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
        },
        "is_identifier": task.field in save.NORMALIZERS,
        "is_cover": task.field == "covers",
        # Offered as one of the cover choices, next to uploading one.
        "cover_suggestion": {"url": AMAZON_COVER.format(isbn10=isbn10), "isbn10": isbn10}
        if task.field == "covers" and (isbn10 := edition.get_isbn10())
        else None,
        "field_guide": field_guide,
        "link_outs": build_link_outs(field_guide, book["isbn13"]),
        # Nothing to compare against when no other edition has a value.
        "siblings": siblings if any(s["value"] for s in siblings) else [],
        "sibling_total": len(others),
        "tally": tally,
        # Quick picks for the answer, only where the other editions are good evidence for this one.
        "suggestions": tally["values"][:3] if field_guide.suggest_from_siblings else [],
        "record_fields": build_work_field_rows(edition, task.field) if task.field in tasks.WORK_FIELDS else build_edition_field_rows(edition, task.field),
        # A judgment: the description, when there is one, is a clue beside the lookups.
        "evidence": build_evidence(edition) if field_guide.choices else None,
        "choices": build_choices(field_guide),
        "list_url": build_dashboard_url(back),
        # Moving on without an answer records nothing; "I couldn't find it" is the one that counts.
        "skip_url": build_next_url(back, task, saved=False),
        "languages": save.language_options() if task.field == "languages" else [],
        "error": error,
        "value": value,
        "note": note,
        # Only "Save and next" brings a receipt; the error re-render never does.
        "receipt": None,
    }


TASK_PATH = rf"/tasks/task/(OL\d+M)/({'|'.join(tasks.POINTS)})"


def get_back_filter(fields: tuple[str, ...]) -> str:
    return normalize_filter(query_param("back", ""), fields)


def require_field_access(user, fld: str) -> None:
    """A beta field is simply not there for anyone off the whitelist."""
    if fld in tasks.BETA_FIELDS and not can_edit_tags(user):
        raise web.notfound()


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
        "contribute/nothing.html.jinja",
        _("Nothing to fill in here"),
        book=build_book_header(edition),
        field_label=label,
        on_work=fld in tasks.WORK_FIELDS,
        list_url=build_dashboard_url(back),
    )


class contribute_task(delegate.page):
    path = TASK_PATH

    def GET(self, olid, fld):
        user = require_login(f"/tasks/task/{olid}/{fld}")
        require_field_access(user, fld)
        back = get_back_filter(fields_for(user))
        edition = get_edition_or_404(olid)
        if not (task := tasks.task_for(edition, fld)):
            return render_nothing_page(edition, fld, back)
        context = build_task_context(edition, task, back) | {"receipt": build_receipt(query_param("saved", ""))}
        return render_contribute("contribute/task.html.jinja", get_field_guides()[fld].question, **context)

    def POST(self, olid, fld):
        user = require_login(f"/tasks/task/{olid}/{fld}")
        require_field_access(user, fld)
        i = web.input(value="", note="", back="", confirmed="", then="", file={})
        # Drop the upload's field storage, as the add-cover page does.
        web.ctx.pop("_fieldstorage", None)
        # Same check as the edit form; it also stops read-only and blocked accounts. The image is not text to check.
        if spamcheck.is_spam(web.storage((k, v) for k, v in i.items() if k != "file"), allow_privileged_edits=True):
            return render_template("message.html", "Oops", "Something went wrong. Please try again later.")
        back = normalize_filter(i.back, fields_for(user))
        edition = get_edition_or_404(olid)
        if not (task := tasks.task_for(edition, fld)):
            return render_nothing_page(edition, fld, back)
        if i.then == "notfound" or (field_guide_choices(fld) and i.value == UNSURE):
            # "Not sure" on a choice list counts like "I couldn't find it": enough people and the gap is set aside.
            initiatives.record_not_found(web.ctx.site, edition.key, fld, user.key)
            if i.then == "next":
                raise web.seeother(build_next_url(back, task, saved=False))
            raise web.seeother(f"/tasks/task/{olid}/{fld}/done?{urlencode({'choice': 'unsure', 'back': back})}")
        done = f"/tasks/task/{olid}/{fld}/done"
        field_guide = get_field_guides()[fld]
        try:
            if field_guide.confirm and not i.confirmed:
                raise save.InvalidAnswer(_("Check that it matches this edition, and tick the box to say so."))
            if fld == "covers":
                save.save_cover(edition, i.file, from_amazon=i.get("cover_choice") == "suggested")
            elif fld in tasks.WORK_FIELDS:
                save.save_work_answer(work_of(edition), fld, i.value, field_guide.label, i.note)
            else:
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
        user = require_login(f"/tasks/task/{olid}/{fld}/done")
        require_field_access(user, fld)
        fields = fields_for(user)
        back = get_back_filter(fields)
        edition = get_edition_or_404(olid)
        field_guides = get_field_guides()
        saved = query_param("choice", "") == "saved"
        same_book = [build_task_summary(t, field_guides, back) for t in tasks.tasks_for_edition(edition) if t.field != fld and t.field in fields]
        # A work answer lands in the work's history.
        edited = work_of(edition) if fld in tasks.WORK_FIELDS and work_of(edition) else edition
        return render_contribute(
            "contribute/done.html.jinja",
            _("Saved") if saved else _("Skipped"),
            book=build_book_header(edition),
            field_label=field_guides[fld].label,
            saved=saved,
            value=format_field_value(edition, fld) if saved else "",
            cover_url=edition.get_cover_url("M") if saved and fld == "covers" else "",
            history_url=f"{edited.key}?m=history",
            same_book=same_book,
            next_url=build_next_url(back, tasks.Task(olid, fld), saved=False),
            list_url=build_dashboard_url(back),
        )
