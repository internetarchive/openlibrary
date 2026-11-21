"""New accounts writing fast: the data behind /admin/new-accounts.

Spam waves come from accounts that are days old at most and start writing within minutes of signing up.
`build_report` finds them from one bounded scan of recent changes and returns plain values for the template.
Most young accounts are not spam, so each one is checked for signs of it (`Signal`). Strong signs make an account
"likely spam", the default view; weak ones only make it "worth a look". The rules come from the accounts admins
reverted as spam (see `find_signals`).
"""

import logging
import re
import traceback
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from openlibrary.i18n import gettext as _
from openlibrary.i18n import ungettext

logger = logging.getLogger("openlibrary.admin.new_accounts")

# Defaults, to be tuned. The first can be overridden per request with ?days=.
MAX_ACCOUNT_AGE_DAYS = 7
MAX_ACCOUNT_AGE_DAYS_LIMIT = 30

MAX_ACCOUNTS = 50  # rows shown
# The newest edits are scanned through Infobase; reading the edit tables directly timed out on production.
# 5,000 reach back about 10 hours there; the page says how far.
MAX_CHANGES_LOADED = 5000
SCAN_PAGE_SIZE = 1000  # changes per Infobase call during the scan
ACCOUNT_HISTORY_LIMIT = 200  # changes loaded for a shown account whose history the scan doesn't cover
RECENT_EDITS_SHOWN = 3
FAST_FIRST_WRITE_MINUTES = 3  # a first write sooner than this after signup is highlighted, though it isn't a signal

# The changeset that creates the profile is the signup itself, not a write.
NON_WRITE_KINDS = ("new-account",)
BOOK_ADD_KINDS = ("add-book",)
# `lists` is the pre-#12226 action; older changesets still carry it.
LIST_CREATE_KINDS = ("lists", "create-list", "create-series")
# Which record of a changeset to show, e.g. the work of an add-book rather than its edition or author.
RECORD_PRIORITY = ("/works/", "/books/", "/lists/", "/series/", "/authors/")
# Adding catalog books to one's own list is what new readers do most; it never counts towards the ranking.
LIST_SEED_KINDS = ("edit-list-seeds",)
# The page is a queue: an account leaves it once an admin blocks it or tags it trusted (which also skips the captcha).
TRUSTED_TAG = "trusted-user"
# Blocked and trusted accounts are looked up newest-changed first (Infobase gives a store row a new id on every put, and
# orders by id), so a young account blocked recently is near the top.
REVIEW_LOOKUP_LIMIT = 1000

# Signals. The records an account created or edited are read, newest first, up to this many, plus its profile.
MAX_RECORDS_CHECKED = 20
BURST_RECORDS = 10  # this many new books or lists ...
BURST_MINUTES = 60  # ... this soon after signup
MANY_LISTS = 3  # readers make one or two lists; spam accounts made up to 100 each
PROFILE_KINDS = ("default-update", "update")
# Uploading covers and photos is catalog work that spam accounts rarely do.
CATALOG_WORK_KINDS = ("add-cover", "add-photo")
# Fields of works, editions, authors, lists and profiles that hold text the account wrote.
TEXT_FIELDS = ("title", "subtitle", "name", "description", "bio", "notes", "first_sentence", "website", "links")
LINK_RE = re.compile(
    r"https?://\S+|www\.\S+|\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:com|net|org|io|info|biz|xyz|top|shop|site|online|club|vip|co|me|ru|cn|in|pk|bd|vn)\b", re.IGNORECASE
)
# Links to these are references, not promotion.
TRUSTED_LINK_DOMAINS = (
    "openlibrary.org",
    "archive.org",
    "wikipedia.org",
    "wikidata.org",
    "wikisource.org",
    "viaf.org",
    "isni.org",
    "orcid.org",
    "loc.gov",
    "worldcat.org",
    "goodreads.com",
    "librarything.com",
    "gutenberg.org",
)
# A run of digits and separators holding 10 to 13 digits: a phone number, unless it is an ISBN.
PHONE_RE = re.compile(r"\+?\(?\d[\d\s().\/-]{8,}\d")
# Wording from the sales and fake-support spam admins reverted: promo codes, casinos, and airline or software "help lines".
SALES_RE = re.compile(
    r"promo ?codes?|coupons?|discount codes?|\d+ ?% ?off\b|casino|betting|\bslots? (?:game|online)|payday|crypto|forex|backlinks?"
    r"|\bseo (?:services?|agency|company)|escorts?\b|call ?girls?|viagra|\bcbd\b|referral codes?|whatsapp"
    r"|customer (?:service|care|support)\W+(?:\w+\W+){0,2}?(?:number|line|phone|contact)|helpline|toll.?free"
    r"|(?:contact|phone|support|change|reservation) numbers?"
    r"|respond quickly|contact methods|(?:speak|talk) (?:to|with) (?:a )?(?:live )?(?:person|agent|human|representative)"
    r"|login (?:not working|issues?)|c[oó]mo (?:hablar|llamar|comunicarse)|gu[ií]a ofic[i]al|\bbuy\b.{0,25}\bonline\b"
    r"|packers and movers|movers and packers|24 ?[x/] ?7",
    re.IGNORECASE,
)
# Headings, bold and links in Markdown: pasted SEO articles.
MARKDOWN_RE = re.compile(r"(?:^|\s)#{1,3} \S|\*\*\S|\[[^\]]+\]\(")
# Ordinary users can't delete these; when one an account created is gone, a librarian removed it.
CATALOG_PREFIXES = ("/works/", "/books/", "/authors/")


@dataclass(frozen=True)
class RecentEdit:
    kind: str
    key: str | None
    title: str | None  # None when the record has no title or is deleted; the template shows the key
    deleted: bool
    undone: bool  # deleted, or changed again since, as a revert does
    timestamp: datetime
    ago: str  # "3.5 h"
    comment: str


@dataclass(frozen=True)
class Signal:
    code: str  # the CSS hook, e.g. "phone"
    label: str
    strong: bool  # one strong signal makes the account likely spam


LIKELY = "likely"
LOOK = "look"
NONE = "none"
REVIEWED = "reviewed"
SHOW_CHOICES = (LIKELY, LOOK, REVIEWED, "all")
# An account's review, once an admin has acted on it.
BLOCKED = "blocked"
REVERTED = "reverted"  # blocked, and its last edits undone
TRUSTED = "trusted"


@dataclass
class AccountRow:
    key: str
    username: str
    displayname: str
    status: str
    email: str | None
    created: datetime
    created_label: str
    age: str
    edits_in_window: int
    edits_in_window_label: str
    books_added: int
    lists_created: int
    list_additions: int  # edits that put books on the account's lists
    other_edits: int
    total_edits: int
    total_edits_label: str
    # False when the account has more history than was loaded: the counts are then minimums and the first write an upper bound.
    exact: bool
    first_write_delay: timedelta
    first_write_label: str
    first_write_is_fast: bool
    recent_edits: list[RecentEdit] = field(default_factory=list)
    signals: list[Signal] = field(default_factory=list)
    tier: str = NONE  # LIKELY, LOOK or NONE
    review: str = ""  # BLOCKED, REVERTED, TRUSTED, or "" while it waits for review


@dataclass
class Report:
    days: int
    age_label: str  # "7 days"
    rows: list[AccountRow]
    matching_accounts: int  # before the cut to `max_accounts`
    likely_accounts: int
    look_accounts: int
    reviewed_accounts: int
    show: str  # LIKELY, LOOK, REVIEWED or "all"
    max_accounts: int
    changes_loaded: int
    capped: bool  # MAX_CHANGES_LOADED was hit, so older edits weren't read
    loaded_back_to_label: str  # the oldest edit read
    error: str = ""  # what broke, when loading failed; there are no rows
    fast_minutes: int = FAST_FIRST_WRITE_MINUTES


def utcnow() -> datetime:
    """Infobase timestamps are naive UTC."""
    return datetime.now(UTC).replace(tzinfo=None)


def clamp_param(value: str | None, default: int, limit: int) -> int:
    """A ?days= override: a whole number from 1 to `limit`, or the default for anything else."""
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


def scan_recent_changes(site, max_changes: int = MAX_CHANGES_LOADED, page_size: int = SCAN_PAGE_SIZE) -> tuple[list, bool]:
    """The newest `max_changes` human changes, newest first.

    :return: the changes, and whether the cap was reached before the changes ran out
    """
    changes: list = []
    seen: set = set()
    offset = 0
    while offset < max_changes:
        limit = min(page_size, max_changes - offset)
        page = site.recentchanges({"bot": False, "limit": limit, "offset": offset})
        # New changes arriving mid-scan push older ones onto the next page a second time.
        changes.extend(c for c in page if c.id not in seen)
        seen.update(c.id for c in page)
        if len(page) < limit:
            return changes, False
        offset += limit
    return changes, True


def load_records(site, keys: list[str]) -> dict:
    """The records at `keys`, by key, in batches of 100. Missing keys are left out."""
    docs: dict = {}
    for start in range(0, len(keys), 100):
        docs.update((doc.key, doc) for doc in site.get_many(keys[start : start + 100]))
    return docs


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


def _ranked_writes(writes) -> int:
    return sum(c.kind not in LIST_SEED_KINDS for c in writes)


def _written_keys(writes) -> tuple[list[str], list[str]]:
    """Records the account created and records it edited that someone else created, each newest first."""
    # A record the account created stays its own even after it edits it again, whichever write comes first.
    seen = dict.fromkeys(c["key"] for change in writes for c in change.changes)
    made = {c["key"] for change in writes for c in change.changes if c.get("revision") == 1}
    return [k for k in seen if k in made], [k for k in seen if k not in made]


def _record_text(doc) -> str:
    parts: list[str] = []
    for name in TEXT_FIELDS:
        value = doc.get(name)
        if isinstance(value, list):
            parts.extend(str(v.get("url") or "") + " " + str(v.get("title") or "") if hasattr(v, "get") else str(v) for v in value)
        elif value:
            parts.append(str(value))
    return " ".join(parts)


def _has_promo_link(text: str) -> bool:
    for match in LINK_RE.finditer(text):
        host = re.sub(r"^(https?://)?(www\.)?", "", match.group(0).lower()).split("/")[0]
        if not any(host == d or host.endswith("." + d) for d in TRUSTED_LINK_DOMAINS):
            return True
    return False


def _has_phone(text: str) -> bool:
    for match in PHONE_RE.finditer(text):
        digits = re.sub(r"\D", "", match.group(0))
        is_isbn = "isbn" in text[max(0, match.start() - 8) : match.start()].lower() or (len(digits) == 13 and digits[:3] in ("978", "979"))
        is_years = all(re.fullmatch(r"(1[5-9]|20)\d\d", group) for group in re.findall(r"\d+", match.group(0)))
        if 10 <= len(digits) <= 13 and not is_isbn and not is_years:
            return True
    return False


def _matches_spam_words(text: str, spam_words: list[str]) -> bool:
    text = text.lower()
    for word in spam_words:
        try:
            if re.search(word.lower(), text):
                return True
        except re.error:
            if word.lower() in text:
                return True
    return False


def tier_of(signals: list[Signal]) -> str:
    if any(s.strong for s in signals):
        return LIKELY
    return LOOK if signals else NONE


def find_signals(site, accounts: dict[str, tuple[datetime, list]], spam_words: list[str]) -> dict[str, list[Signal]]:
    """Signs of spam for each account, from what it wrote: `accounts` maps a profile key to (signup time, writes newest first).

    Tuned on the 861 accounts admins reverted as spam from Aug 2025 to Nov 2026, against new accounts that weren't:
    the strong signals mark 86% of the spam accounts and none of 42 ordinary new accounts.
    Not signals, though spam has them too: a first write within minutes of signup, and list additions.
    Most new readers do both.
    """
    written = {key: _written_keys(writes) for key, (_, writes) in accounts.items()}
    checked = {key: (created[:MAX_RECORDS_CHECKED], edited[:MAX_RECORDS_CHECKED]) for key, (created, edited) in written.items()}
    docs = load_records(site, sorted({k for created, edited in checked.values() for k in created + edited} | set(accounts)))

    def live(keys) -> list:
        return [docs[k] for k in keys if k in docs and docs[k].type.key != "/type/delete"]

    signals = {}
    for key, (signup, writes) in accounts.items():
        created, edited = checked[key]
        # What the account wrote itself: its profile and new records. Edited records also hold other people's text,
        # so only wording that never belongs in a catalog record (phone numbers, sales pitches) counts there.
        own = [_record_text(doc) for doc in live([key, *created])]
        everything = own + [_record_text(doc) for doc in live(edited)]
        kinds = {c.kind for c in writes}
        catalog_work = bool(kinds & set(CATALOG_WORK_KINDS))
        only_profile = kinds <= set(PROFILE_KINDS) and all(c["key"] == key for w in writes for c in w.changes)

        found = []
        if phones := sum(map(_has_phone, everything)):
            label = ungettext("Phone number in %(count)s record", "Phone numbers in %(count)s records", phones, count=phones)
            # A publisher's contact number next to real catalog work is self-promotion, not spam.
            found.append(Signal("phone", label, strong=not catalog_work))
        if sales := sum(bool(SALES_RE.search(t)) for t in everything):
            found.append(
                Signal(
                    "sales",
                    ungettext("Sales or support-line wording in %(count)s record", "Sales or support-line wording in %(count)s records", sales, count=sales),
                    strong=True,
                )
            )
        if spam_words and (with_words := sum(_matches_spam_words(t, spam_words) for t in everything)):
            found.append(
                Signal("spam-words", ungettext("Spam words in %(count)s record", "Spam words in %(count)s records", with_words, count=with_words), strong=True)
            )
        if (lists := sum(c.kind in LIST_CREATE_KINDS for c in writes)) >= MANY_LISTS:
            found.append(Signal("lists", _("%(count)s lists created", count=lists), strong=True))
        if deleted := sum(k.startswith(CATALOG_PREFIXES) and k in docs and docs[k].type.key == "/type/delete" for k in created):
            found.append(
                Signal("deleted", ungettext("%(count)s record already deleted", "%(count)s records already deleted", deleted, count=deleted), strong=True)
            )
        if links := sum(map(_has_promo_link, own)):
            if only_profile:
                found.append(Signal("profile-link", _("Only edit: a link on their profile"), strong=True))
            else:
                found.append(Signal("links", ungettext("Links in %(count)s record", "Links in %(count)s records", links, count=links), strong=False))
        if markdown := sum(bool(MARKDOWN_RE.search(t)) for t in own):
            found.append(
                Signal(
                    "markdown",
                    ungettext("Article formatting in %(count)s record", "Article formatting in %(count)s records", markdown, count=markdown),
                    strong=False,
                )
            )
        burst_end = signup + timedelta(minutes=BURST_MINUTES)
        if (burst := sum(c.kind in BOOK_ADD_KINDS + LIST_CREATE_KINDS and c.timestamp <= burst_end for c in writes)) >= BURST_RECORDS:
            found.append(Signal("burst", _("%(count)s added in the first %(minutes)s min", count=burst, minutes=BURST_MINUTES), strong=False))
        found.sort(key=lambda s: not s.strong)
        signals[key] = found
    return signals


def _recent_edits(site, writes_by_author: dict[str, list], now: datetime) -> dict[str, list[RecentEdit]]:
    """The newest few writes of every account, their records' titles fetched in one batch."""
    newest = {author: writes[:RECENT_EDITS_SHOWN] for author, writes in writes_by_author.items()}
    keys = {key for writes in newest.values() for c in writes if (key := _primary_key(c))}
    docs = {doc.key: doc for doc in site.get_many(sorted(keys))}

    def edit(change) -> RecentEdit:
        key = _primary_key(change)
        doc = docs.get(key)
        deleted = doc is not None and doc.type.key == "/type/delete"
        revision = next((item.get("revision") for item in change.changes if item.get("key") == key), None)
        title = doc is not None and not deleted and (doc.get("title") or doc.get("name") or doc.get("displayname"))
        return RecentEdit(
            kind=change.kind,
            key=key,
            title=str(title) if title else None,
            deleted=deleted,
            undone=deleted or bool(doc is not None and revision and doc.revision > revision),
            timestamp=change.timestamp,
            ago=format_duration(now - change.timestamp),
            comment=change.comment or "",
        )

    return {author: [edit(c) for c in writes] for author, writes in newest.items()}


def _accounts_with(site, name: str, value: str) -> set[str]:
    """Profile keys of the accounts whose store record has `name` equal to, or holding, `value`."""
    keys = site.store.keys(type="account", name=name, value=value, limit=REVIEW_LOOKUP_LIMIT)
    return {"/people/" + key.removeprefix("account/") for key in keys}


def build_report(site, **kwargs) -> Report:
    """`_build_report`, or an empty report naming the exception, so admins see what broke instead of a 500."""
    try:
        return _build_report(site, **kwargs)
    except Exception as e:
        logger.exception("Spam review failed to load")
        frame = traceback.extract_tb(e.__traceback__)[-1]
        days = kwargs.get("days", MAX_ACCOUNT_AGE_DAYS)
        return Report(
            days=days,
            age_label=ungettext("%(count)s day", "%(count)s days", days, count=days),
            rows=[],
            matching_accounts=0,
            likely_accounts=0,
            look_accounts=0,
            reviewed_accounts=0,
            show=kwargs.get("show", "all"),
            max_accounts=kwargs.get("max_accounts", MAX_ACCOUNTS),
            changes_loaded=0,
            capped=False,
            loaded_back_to_label="",
            error=f"{type(e).__name__}: {e} ({frame.filename.rsplit('/', 1)[-1]}:{frame.lineno})",
        )


def _build_report(
    site,
    now: datetime | None = None,
    days: int = MAX_ACCOUNT_AGE_DAYS,
    max_accounts: int = MAX_ACCOUNTS,
    max_changes: int = MAX_CHANGES_LOADED,
    page_size: int = SCAN_PAGE_SIZE,
    history_limit: int = ACCOUNT_HISTORY_LIMIT,
    show: str = "all",
    spam_words: list[str] | None = None,
) -> Report:
    """Accounts under `days` days old among the newest `max_changes` edits, likely spam first, then most writes.

    `show` limits the rows to one queue: LIKELY or LOOK, the accounts of that tier still waiting for review;
    REVIEWED, those blocked or trusted; or "all".

    Cost, in Infobase calls: the scan (at most max_changes / page_size), one `get_many` per 100 authors seen in it,
    one `get_many` per 100 records the signals read (up to 2 * MAX_RECORDS_CHECKED + 1 per young account), two store
    queries for the blocked and trusted accounts, and for the `max_accounts` rows shown: one store read each, one
    `recentchanges` for each that signed up before the scan's reach, and one `get_many` for the titles of the last edits.
    """
    now = now or utcnow()
    signup_cutoff = now - timedelta(days=days)
    labels = {
        "days": days,
        "age_label": ungettext("%(count)s day", "%(count)s days", days, count=days),
        "show": show,
        "max_accounts": max_accounts,
    }

    changes, capped = scan_recent_changes(site, max_changes=max_changes, page_size=page_size)
    loaded_back_to = changes[-1].timestamp if changes else None

    scanned: dict[str, list] = {}
    for change in _writes(changes):
        if change.author is not None:
            scanned.setdefault(change.author.key, []).append(change)

    # Bot accounts and display names come from the profile, loaded in batches.
    young = {}
    for user in load_records(site, sorted(scanned)).values():
        created = _as_datetime(getattr(user, "created", None))
        if user.type.key == "/type/user" and not user.get("bot") and created and created >= signup_cutoff:
            young[user.key] = (user, created)

    def first_delay(key: str) -> timedelta:
        return max(scanned[key][-1].timestamp - young[key][1], timedelta(0))

    signals = find_signals(site, {key: (young[key][1], scanned[key]) for key in young}, spam_words or [])
    tiers = {key: tier_of(signals[key]) for key in young}
    order = {LIKELY: 0, LOOK: 1, NONE: 2}
    reviewed = (_accounts_with(site, "status", "blocked") | _accounts_with(site, "tags", TRUSTED_TAG)) & young.keys()

    def in_queue(key: str) -> bool:
        if show == REVIEWED:
            return key in reviewed
        return show == "all" or (tiers[key] == show and key not in reviewed)

    def rank(key: str):
        return (order[tiers[key]], -sum(s.strong for s in signals[key]), -_ranked_writes(scanned[key]), first_delay(key))

    shown = sorted(filter(in_queue, young), key=rank)[:max_accounts]

    history: dict[str, list] = {}
    exact_authors: set[str] = set()
    for key in shown:
        writes = scanned[key]
        # The scan holds an account's whole history if it ran out of changes, or the account signed up within its reach.
        if not capped or (loaded_back_to and young[key][1] >= loaded_back_to):
            exact_authors.add(key)
        else:
            loaded = site.recentchanges({"author": key, "limit": history_limit})
            # Both lists are the account's newest writes, so the longer one holds the other.
            writes = max(_writes(loaded), writes, key=len)
            if len(loaded) < history_limit:
                exact_authors.add(key)
        history[key] = writes
    recent_edits = _recent_edits(site, history, now)

    rows = []
    for key in shown:
        user, created = young[key]
        # The scan holds every edit back to where it stopped, so the count within it is exact.
        writes, window = history[key], scanned[key]
        exact = key in exact_authors
        username = key.split("/")[-1]
        account = site.store.get(f"account/{username}") or {}
        status = account.get("status") or "unknown"
        edits = recent_edits[key]
        if status == "blocked":
            review = REVERTED if edits and all(e.undone for e in edits) else BLOCKED
        else:
            review = TRUSTED if TRUSTED_TAG in (account.get("tags") or []) else ""

        books_added = sum(c.kind in BOOK_ADD_KINDS for c in window)
        lists_created = sum(c.kind in LIST_CREATE_KINDS for c in window)
        list_additions = sum(c.kind in LIST_SEED_KINDS for c in window)
        delay = max(writes[-1].timestamp - created, timedelta(0))
        delay_label = format_duration(delay)

        rows.append(
            AccountRow(
                key=key,
                username=username,
                displayname=str(user.get("displayname") or username),
                status=status,
                email=account.get("email"),
                created=created,
                created_label=_timestamp_label(created),
                age=format_duration(now - created),
                edits_in_window=len(window),
                edits_in_window_label=str(len(window)),
                books_added=books_added,
                lists_created=lists_created,
                list_additions=list_additions,
                other_edits=len(window) - books_added - lists_created - list_additions,
                total_edits=len(writes),
                total_edits_label=str(len(writes)) if exact else f"{len(writes)}+",
                exact=exact,
                first_write_delay=delay,
                first_write_label=delay_label if exact else _("at most %(duration)s", duration=delay_label),
                first_write_is_fast=delay < timedelta(minutes=FAST_FIRST_WRITE_MINUTES),
                recent_edits=edits,
                signals=signals[key],
                tier=tiers[key],
                review=review,
            )
        )

    return Report(
        **labels,
        rows=rows,
        matching_accounts=len(young),
        likely_accounts=sum(t == LIKELY and k not in reviewed for k, t in tiers.items()),
        look_accounts=sum(t == LOOK and k not in reviewed for k, t in tiers.items()),
        reviewed_accounts=len(reviewed),
        changes_loaded=len(changes),
        capped=capped,
        loaded_back_to_label=_timestamp_label(loaded_back_to) if loaded_back_to else "",
    )
