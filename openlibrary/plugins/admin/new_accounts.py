"""New accounts writing fast: the data behind /admin/new-accounts.

Spam waves come from accounts that are days old at most and start writing within minutes of signing up.
`build_report` finds them from one bounded scan of recent changes and returns plain values for the template.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from openlibrary.i18n import gettext as _
from openlibrary.i18n import ungettext

# Defaults, to be tuned. The first two can be overridden per request with ?days= and ?hours=.
MAX_ACCOUNT_AGE_DAYS = 7
WINDOW_HOURS = 24
MAX_ACCOUNT_AGE_DAYS_LIMIT = 30
WINDOW_HOURS_LIMIT = 72

MAX_ACCOUNTS = 50  # rows shown
MAX_CHANGES_SCANNED = 5000  # hard cap on the scan of the window; the page says when it was hit
SCAN_PAGE_SIZE = 1000  # changes per Infobase call during the scan
ACCOUNT_HISTORY_LIMIT = 200  # changes loaded for an account whose history the scan doesn't cover
RECENT_EDITS_SHOWN = 3
FAST_FIRST_WRITE_MINUTES = 10  # a first write sooner than this after signup is highlighted

# The changeset that creates the profile is the signup itself, not a write.
NON_WRITE_KINDS = ("new-account",)
BOOK_ADD_KINDS = ("add-book",)
# `lists` is the pre-#12226 action; older changesets still carry it.
LIST_CREATE_KINDS = ("lists", "create-list", "create-series")
# Which record of a changeset to show, e.g. the work of an add-book rather than its edition or author.
RECORD_PRIORITY = ("/works/", "/books/", "/lists/", "/series/", "/authors/")
BLOCKABLE_STATUSES = ("active", "verified")


@dataclass(frozen=True)
class RecentEdit:
    kind: str
    key: str | None
    title: str | None  # None when the record has no title or is deleted; the template shows the key
    deleted: bool
    timestamp: datetime
    ago: str  # "3.5 h"
    comment: str


@dataclass
class AccountRow:
    key: str
    username: str
    displayname: str
    status: str
    email: str | None
    can_block: bool
    created: datetime
    created_label: str
    age: str
    edits_in_window: int
    edits_in_window_label: str
    books_added: int
    lists_created: int
    other_edits: int
    total_edits: int
    total_edits_label: str
    # False when the account has more history than was loaded: the counts are then minimums and the first write an upper bound.
    exact: bool
    first_write_delay: timedelta
    first_write_label: str
    first_write_is_fast: bool
    recent_edits: list[RecentEdit] = field(default_factory=list)


@dataclass
class Report:
    days: int
    hours: int
    age_label: str  # "7 days"
    window_label: str  # "24 hours"
    rows: list[AccountRow]
    matching_accounts: int  # before the cut to `max_accounts`
    max_accounts: int
    changes_scanned: int
    scan_capped: bool
    scanned_back_to: datetime | None  # the oldest change the scan reached
    scanned_back_to_label: str
    fast_minutes: int = FAST_FIRST_WRITE_MINUTES


def utcnow() -> datetime:
    """Infobase timestamps are naive UTC."""
    return datetime.now(UTC).replace(tzinfo=None)


def clamp_param(value: str | None, default: int, limit: int) -> int:
    """A ?days= or ?hours= override: a whole number from 1 to `limit`, or the default for anything else."""
    try:
        number = int(value or "")
    except ValueError:
        return default
    return number if 1 <= number <= limit else default


def format_duration(delta: timedelta) -> str:
    """A span short enough to compare down a column: "45 s", "2.1 min", "34 min", "3.5 h", "12 d"."""

    def amount(value: float) -> str:
        return f"{value:.1f}" if value < 10 else f"{value:.0f}"

    seconds = max(delta.total_seconds(), 0)
    if seconds < 60:
        return _("%(n)s s", n=int(seconds))
    if seconds < 3600:
        return _("%(n)s min", n=amount(seconds / 60))
    if seconds < 48 * 3600:
        return _("%(n)s h", n=amount(seconds / 3600))
    return _("%(n)s d", n=amount(seconds / 86400))


def scan_recent_changes(site, since: datetime, max_changes: int = MAX_CHANGES_SCANNED, page_size: int = SCAN_PAGE_SIZE) -> tuple[list, bool]:
    """Human changes since `since`, newest first, stopping at `max_changes`.

    :return: the changes, and whether the cap was reached before the window was exhausted
    """
    changes: list = []
    seen: set = set()
    offset = 0
    while offset < max_changes:
        limit = min(page_size, max_changes - offset)
        page = site.recentchanges({"begin_date": since.isoformat(), "bot": False, "limit": limit, "offset": offset})
        # New changes arriving mid-scan push older ones onto the next page a second time.
        changes.extend(c for c in page if c.id not in seen)
        seen.update(c.id for c in page)
        if len(page) < limit:
            return changes, False
        offset += limit
    return changes, True


def _writes(changes) -> list:
    return [c for c in changes if c.kind not in NON_WRITE_KINDS]


def _as_datetime(value) -> datetime | None:
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value.replace(tzinfo=None) if isinstance(value, datetime) else None


def _timestamp_label(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M")


def _primary_key(change) -> str | None:
    # A key becomes a link, so only site paths qualify.
    keys = [c["key"] for c in change.changes if c["key"].startswith("/") and not c["key"].startswith("//")]
    for prefix in RECORD_PRIORITY:
        for key in keys:
            if prefix in key:
                return key
    return keys[0] if keys else None


def _recent_edits(site, writes_by_author: dict[str, list], now: datetime) -> dict[str, list[RecentEdit]]:
    """The newest few writes of every account, their records' titles fetched in one batch."""
    newest = {author: writes[:RECENT_EDITS_SHOWN] for author, writes in writes_by_author.items()}
    keys = {key for writes in newest.values() for c in writes if (key := _primary_key(c))}
    docs = {doc.key: doc for doc in site.get_many(sorted(keys))}

    def edit(change) -> RecentEdit:
        key = _primary_key(change)
        doc = docs.get(key)
        deleted = doc is not None and doc.type.key == "/type/delete"
        title = doc is not None and not deleted and (doc.get("title") or doc.get("name") or doc.get("displayname"))
        return RecentEdit(
            kind=change.kind,
            key=key,
            title=str(title) if title else None,
            deleted=deleted,
            timestamp=change.timestamp,
            ago=format_duration(now - change.timestamp),
            comment=change.comment or "",
        )

    return {author: [edit(c) for c in writes] for author, writes in newest.items()}


def build_report(
    site,
    now: datetime | None = None,
    days: int = MAX_ACCOUNT_AGE_DAYS,
    hours: int = WINDOW_HOURS,
    max_accounts: int = MAX_ACCOUNTS,
    max_changes: int = MAX_CHANGES_SCANNED,
    page_size: int = SCAN_PAGE_SIZE,
    history_limit: int = ACCOUNT_HISTORY_LIMIT,
) -> Report:
    """Accounts under `days` days old that wrote in the last `hours` hours, most writes first.

    Cost, in Infobase calls: the scan (at most max_changes / page_size), one `get_many` per 100 authors seen in it,
    and then for the `max_accounts` rows shown: one store read each for status and email, one `recentchanges` for
    each account that signed up before the scan's reach, and one `get_many` for the titles of the last edits.
    """
    now = now or utcnow()
    since = now - timedelta(hours=hours)
    signup_cutoff = now - timedelta(days=days)

    changes, scan_capped = scan_recent_changes(site, since, max_changes=max_changes, page_size=page_size)
    scanned_back_to = changes[-1].timestamp if changes else None

    scanned_by_author: dict[str, list] = {}
    for change in _writes(changes):
        if change.author is not None:
            scanned_by_author.setdefault(change.author.key, []).append(change)

    # Account age comes from the profile, so every author seen is loaded once, in batches.
    young = {}
    for user in site.get_many(sorted(scanned_by_author)):
        created = _as_datetime(getattr(user, "created", None))
        if user.type.key == "/type/user" and not user.get("bot") and created and created >= signup_cutoff:
            young[user.key] = (user, created)

    def first_delay(key: str) -> timedelta:
        return scanned_by_author[key][-1].timestamp - young[key][1]

    ranked = sorted(young, key=lambda key: (-len(scanned_by_author[key]), first_delay(key)))
    shown = ranked[:max_accounts]

    # The scan holds an account's whole history only if it signed up within the scan's reach.
    scan_reach = scanned_back_to if scan_capped and scanned_back_to else since
    writes_by_author: dict[str, list] = {}
    exact_authors: set[str] = set()
    for key in shown:
        writes = scanned_by_author[key]
        if young[key][1] >= scan_reach:
            exact_authors.add(key)
        else:
            history = site.recentchanges({"author": key, "limit": history_limit})
            # Both lists are the account's newest writes, so the longer one holds the other.
            writes = max(_writes(history), writes, key=len)
            if len(history) < history_limit:
                exact_authors.add(key)
        writes_by_author[key] = writes

    recent_edits = _recent_edits(site, writes_by_author, now)

    rows = []
    for key in shown:
        user, created = young[key]
        writes = writes_by_author[key]
        exact = key in exact_authors
        username = key.split("/")[-1]
        account = site.store.get(f"account/{username}") or {}
        status = account.get("status") or "unknown"

        in_window = [c for c in writes if c.timestamp >= since]
        books_added = sum(c.kind in BOOK_ADD_KINDS for c in in_window)
        lists_created = sum(c.kind in LIST_CREATE_KINDS for c in in_window)
        # The loaded history may stop inside the window only if the scan did too.
        window_is_minimum = not exact and scan_capped and writes[-1].timestamp >= since
        delay = max(writes[-1].timestamp - created, timedelta(0))
        delay_label = format_duration(delay)

        rows.append(
            AccountRow(
                key=key,
                username=username,
                displayname=str(user.get("displayname") or username),
                status=status,
                email=account.get("email"),
                can_block=status in BLOCKABLE_STATUSES,
                created=created,
                created_label=_timestamp_label(created),
                age=format_duration(now - created),
                edits_in_window=len(in_window),
                edits_in_window_label=f"{len(in_window)}+" if window_is_minimum else str(len(in_window)),
                books_added=books_added,
                lists_created=lists_created,
                other_edits=len(in_window) - books_added - lists_created,
                total_edits=len(writes),
                total_edits_label=str(len(writes)) if exact else f"{len(writes)}+",
                exact=exact,
                first_write_delay=delay,
                first_write_label=delay_label if exact else _("at most %(duration)s", duration=delay_label),
                first_write_is_fast=delay < timedelta(minutes=FAST_FIRST_WRITE_MINUTES),
                recent_edits=recent_edits[key],
            )
        )

    rows.sort(key=lambda row: (-row.edits_in_window, row.first_write_delay))
    return Report(
        days=days,
        hours=hours,
        age_label=ungettext("%(count)s day", "%(count)s days", days, count=days),
        window_label=ungettext("%(count)s hour", "%(count)s hours", hours, count=hours),
        rows=rows,
        matching_accounts=len(young),
        max_accounts=max_accounts,
        changes_scanned=len(changes),
        scan_capped=scan_capped,
        scanned_back_to=scanned_back_to,
        scanned_back_to_label=_timestamp_label(scanned_back_to) if scanned_back_to else "",
    )
