"""Side-by-side comparison of the two "books like this one" queries, at
/developers/more-like-this.

The work page's related-books carousel finds similar books by OR-ing the work's
subjects together (see templates/books/RelatedWorksCarousel.html). Solr's
more-like-this parser, reached through the `like:` search field, picks its own
terms from the seed work instead, weighting them by how distinctive they are.
The two disagree often enough that the only way to judge them is to look at a
sample of books side by side.

The queries are built here, server-side, because the baseline has to reuse the
real `get_related_books_subjects()` to be a fair comparison. They are *run* from
the browser: a sample of ten books is twenty solr queries, and issuing those
serially while the page waits would make it unusable. The template fetches each
from /search.json and reports its own timing.

Two things make a comparison repeatable. The more-like-this tuning is read from
`mlt_*` url params, which are ordinary `SolrInternalsParams` and so reach solr
through the same gated path as the edismax A/B knobs — meaning a tuning tried
here can be reproduced against /search.json with curl. And `works=OL1W,OL2W`
pins the comparison set instead of sampling, which is what the share link
builds, so two people can argue about the same books.
"""

import logging
import random
import re
from dataclasses import dataclass, field
from urllib.parse import urlencode

import web
from pydantic import ValidationError

from infogami.utils import delegate
from infogami.utils.view import render_template
from openlibrary import accounts
from openlibrary.core.bookshelves import Bookshelves
from openlibrary.fastapi.models import SolrInternalsParams
from openlibrary.plugins.worksearch.code import run_solr_query
from openlibrary.plugins.worksearch.schemes.works import MLT_LOCAL_PARAMS, WorkSearchScheme

logger = logging.getLogger("openlibrary.more_like_this")

# Only borrowable-or-better books are worth recommending, and the real carousel
# filters the same way, so both sides of the comparison inherit it.
AVAILABILITY_FILTER = "ebook_access:[borrowable TO *]"

COUNT_CHOICES = (5, 10, 20)
DEFAULT_COUNT = 10

ALREADY_READ = Bookshelves.PRESET_BOOKSHELVES["Already Read"]

# Ceiling on the reading-log pool, which becomes one `key:(...)` clause. Well
# under solr's boolean-clause limit, and a reader with more read books than this
# loses nothing that matters — it is still a sample either way.
MAX_READ_SEEDS = 300

# Ceiling on a shared comparison set, so a hand-edited `works=` can't turn one
# page load into an unbounded pile of queries.
MAX_PINNED_WORKS = 50

re_work_olid = re.compile(r"OL\d+W")


@dataclass(frozen=True)
class Choice:
    """One option in a dropdown: the value that goes in the URL, and its label."""

    id: str
    label: str


# How to pick the sample. Each maps to a sort understood by
# `WorkSearchScheme.process_user_sort`; "random" gets a fresh seed per request
# so that pressing Go actually re-rolls (see `_sample_sort`).
METHODS = (
    Choice("random", "Random"),
    Choice("trending", "Trending"),
    Choice("editions", "Most editions"),
)

# Which books to pick from. A pool is just the `q` the sample is drawn from.
POOLS = (
    Choice("all", "All books"),
    Choice("popular", "Popular books"),
    Choice("read", "Books I've read"),
)

STATIC_POOL_QUERIES = {
    # Every work that could plausibly be recommended. Restricted to books with
    # subjects, since the baseline query has nothing to work with otherwise and
    # the row would compare against an empty carousel.
    "all": f"{AVAILABILITY_FILTER} subject:*",
    # Books readers have actually shelved. Skews the sample towards the
    # well-catalogued end, where both queries have the most to go on.
    "popular": f"{AVAILABILITY_FILTER} subject:* readinglog_count:[5 TO *]",
}


@dataclass
class Row:
    """One sampled book, with the two queries to compare for it."""

    key: str
    title: str
    authors: str
    year: str
    cover_id: str
    # The query the work page's carousel would run. Empty when the work has no
    # usable subjects — worth seeing rather than hiding, since `like:` still
    # has title and author to go on and this is exactly where the two diverge.
    baseline_query: str
    mlt_query: str
    subjects: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class MltControl:
    """One more-like-this tuning knob, as the page renders it."""

    # The url param, e.g. "mlt_mintf".
    param: str
    # The solr local param it becomes, e.g. "mintf".
    name: str
    value: str
    default: str
    help: str

    @property
    def is_default(self) -> bool:
        return self.value == self.default


@dataclass
class Context:
    """Everything the template needs."""

    count: int
    method: str
    pool: str
    rows: list[Row] = field(default_factory=list)
    counts: tuple[int, ...] = COUNT_CHOICES
    methods: tuple[Choice, ...] = METHODS
    pools: tuple[Choice, ...] = POOLS
    mlt_controls: list[MltControl] = field(default_factory=list)
    # A link that reproduces this exact comparison — same books, same tuning.
    share_url: str = ""
    # True when the books came from a `works=` param rather than a fresh sample.
    pinned: bool = False
    # Set when the sample came back empty, so the page can say why rather than
    # rendering nothing. Local dev indexes are small and often lack the
    # trending/readinglog data the non-default methods sort on.
    message: str = ""


def _label(choices: tuple[Choice, ...], choice_id: str) -> str:
    return next(choice.label for choice in choices if choice.id == choice_id)


def _mlt_controls(supplied: dict[str, str]) -> list[MltControl]:
    """The tuning knobs, each carrying its current value and its explanation.

    Both come from elsewhere on purpose: the defaults are whatever the `like:`
    field actually uses, and the help text is the pydantic field description, so
    neither can drift from the behaviour the page is demonstrating.
    """
    controls = []
    for param in SolrInternalsParams.mlt_fields():
        name = param[len("mlt_") :]
        default = MLT_LOCAL_PARAMS.get(name, "")
        controls.append(
            MltControl(
                param=param,
                name=name,
                value=supplied.get(param, default),
                default=default,
                help=SolrInternalsParams.model_fields[param].description or "",
            )
        )
    return controls


def _sample_sort(method: str) -> str:
    """The solr sort for a sampling method.

    Random gets a per-request seed: solr's `random_*` fields are seeded by name,
    so a fixed `random` sort would hand back the same books every time and make
    the Go button look broken.
    """
    if method == "random":
        return f"random_{random.randint(0, 10**6)}"
    return method


def _baseline_query(work, work_key: str) -> str:
    """The query behind "Available books like this one" on the work page.

    Kept in step with templates/books/RelatedWorksCarousel.html, and reusing the
    same subject filtering, so the left-hand carousel really is the status quo
    rather than an approximation of it.
    """
    subjects = work.get_related_books_subjects()
    if not subjects:
        return ""
    quoted = " OR ".join(f'"{subject}"' for subject in subjects)
    query = f'{AVAILABILITY_FILTER} -key:"{work_key}" subject:({quoted})'
    if author_keys := [author.key.split("/")[-1] for author in work.get_authors()]:
        query += f" -author_key:({' OR '.join(author_keys)})"
    return query


def _mlt_query(work, work_key: str) -> str:
    """The same slot, asked for with `like:`.

    Carries the baseline's availability filter and author exclusion so the two
    carousels differ only in how similarity is decided, not in what is eligible.
    """
    query = f"like:{work_key} {AVAILABILITY_FILTER}"
    if author_keys := [author.key.split("/")[-1] for author in work.get_authors()]:
        query += f" -author_key:({' OR '.join(author_keys)})"
    return query


def _read_work_keys(username: str) -> list[str]:
    """Work keys on the reader's "Already Read" shelf, newest first.

    Filtered out of the shared iterator rather than queried directly: it pages
    in blocks and this stops at the cap, so a heavy reading log costs a couple
    of queries instead of a full scan.
    """
    keys = []
    for row in Bookshelves.iterate_users_logged_books(username):
        if row["bookshelf_id"] != ALREADY_READ:
            continue
        keys.append(f"/works/OL{row['work_id']}W")
        if len(keys) >= MAX_READ_SEEDS:
            break
    return keys


def _pool_query(pool: str) -> tuple[str, str]:
    """The solr `q` to draw seeds from, or ``("", reason)`` if the pool is unusable."""
    if pool != "read":
        return STATIC_POOL_QUERIES[pool], ""

    if not (user := accounts.get_current_user()):
        return "", "Log in to sample from the books you've read."
    if not (keys := _read_work_keys(user.key.split("/")[-1])):
        return "", "Nothing on your “Already Read” shelf yet, so there would be no results you could judge."

    # Deliberately unfiltered, unlike the other pools: a reader's own judgement
    # is the scarce thing here, so don't drop their read books for being
    # unborrowable or subject-less. A subject-less row is worth keeping rather
    # than hiding — the baseline can offer nothing at all for one, so the row
    # shows whether `like:` does any better from title and author alone.
    keys_clause = " OR ".join(f'"{key}"' for key in keys)
    return f"key:({keys_clause})", ""


SEED_FIELDS = [
    "key",
    "title",
    "author_name",
    "first_publish_year",
    "cover_i",
    "subject",
]


def _seed_docs(query: str, rows: int, sort: str | None) -> list:
    response = run_solr_query(
        WorkSearchScheme(),
        {"q": query},
        rows=rows,
        sort=sort,
        fields=SEED_FIELDS,
        facet=False,
        spellcheck_count=0,
        request_label="MORE_LIKE_THIS_SAMPLE",
    )
    return response.docs


def _build_rows(docs: list) -> list[Row]:
    rows = []
    for doc in docs:
        work_key = doc["key"]
        # The baseline's subject list comes from the work record rather than
        # solr, so that it matches what the work page itself would build.
        if (work := web.ctx.site.get(work_key)) is None:
            logger.warning("Sampled work %s is in solr but not the db; skipping", work_key)
            continue
        rows.append(
            Row(
                key=work_key,
                title=doc.get("title", work_key),
                authors=", ".join(doc.get("author_name", [])),
                year=str(doc.get("first_publish_year") or ""),
                cover_id=str(doc.get("cover_i") or ""),
                baseline_query=_baseline_query(work, work_key),
                mlt_query=_mlt_query(work, work_key),
                subjects=doc.get("subject", [])[:12],
            )
        )
    return rows


def _sample(count: int, method: str, pool_query: str) -> list[Row]:
    return _build_rows(_seed_docs(pool_query, count, _sample_sort(method)))


def _pinned_works(olids: list[str]) -> list[Row]:
    """The named works, in the order given, so a shared link is stable."""
    keys = [f"/works/{olid}" for olid in olids]
    keys_clause = " OR ".join(f'"{key}"' for key in keys)
    docs_by_key = {doc["key"]: doc for doc in _seed_docs(f"key:({keys_clause})", len(keys), None)}
    return _build_rows([docs_by_key[key] for key in keys if key in docs_by_key])


def _parse_works(raw: str) -> list[str]:
    """Work OLIDs out of a `works=` param, accepting keys or bare OLIDs."""
    found = []
    for part in raw.split(","):
        if match := re_work_olid.search(part.strip().upper()):
            found.append(match.group(0))
    # dict.fromkeys rather than set(): a shared link's order is meaningful.
    return list(dict.fromkeys(found))[:MAX_PINNED_WORKS]


def _share_url(rows: list[Row], supplied_mlt: dict[str, str]) -> str:
    """A link that reproduces this comparison for someone else.

    Carries the books rather than the sampling that found them, so the link
    keeps working (and keeps showing the same books) however the index changes.
    """
    params = {"works": ",".join(row.key.removeprefix("/works/") for row in rows), **supplied_mlt, "go": "1"}
    return "/developers/more-like-this?" + urlencode(params)


def build_context() -> Context:
    params = web.input(count=str(DEFAULT_COUNT), method="random", pool="all", works="", go="")

    try:
        count = int(params.count)
    except ValueError:
        count = DEFAULT_COUNT
    count = count if count in COUNT_CHOICES else DEFAULT_COUNT

    method = params.method if params.method in {choice.id for choice in METHODS} else "random"
    pool = params.pool if params.pool in {choice.id for choice in POOLS} else "all"

    # Only the knobs actually named in the url, so the share link and the
    # /search.json calls carry a tuning rather than a restatement of defaults.
    supplied_mlt = {param: value for param in SolrInternalsParams.mlt_fields() if (value := web.input(**{param: ""}).get(param))}

    context = Context(count=count, method=method, pool=pool, mlt_controls=_mlt_controls(supplied_mlt))

    # Report a bad knob once, here, rather than as an identical failed fetch in
    # every carousel on the page.
    try:
        SolrInternalsParams.model_validate(supplied_mlt)
    except ValidationError as e:
        error = e.errors()[0]
        context.message = f"Invalid tuning value for {error['loc'][0]}: {error['msg']}"
        return context

    if params.works:
        olids = _parse_works(params.works)
        if not olids:
            context.message = f"No work ids found in works={params.works!r}. Expected something like 'OL1W,OL2W'."
            return context
        context.pinned = True
        context.rows = _pinned_works(olids)
        missing = len(olids) - len(context.rows)
        if not context.rows:
            context.message = "None of the shared works are in this search index."
        elif missing:
            # Say so: otherwise a shared link quietly compares fewer books than
            # the person who sent it was looking at.
            context.message = f"{missing} of the {len(olids)} shared works {'is' if missing == 1 else 'are'} not in this search index."
        context.share_url = _share_url(context.rows, supplied_mlt)
        return context

    # Nothing is sampled until Go is pressed, so arriving at the page doesn't
    # fire a solr query plus a db read per book.
    if not params.go:
        return context

    pool_query, unusable = _pool_query(pool)
    if unusable:
        context.message = unusable
        return context

    context.rows = _sample(count, method, pool_query)
    if not context.rows:
        pool_label = _label(POOLS, pool)
        method_label = _label(METHODS, method)
        context.message = (
            f"No books matched the {pool_label!r} pool sorted by {method_label!r}. A small dev index often has no trending or readinglog data to sort on."
        )
    context.share_url = _share_url(context.rows, supplied_mlt) if context.rows else ""
    return context


class more_like_this(delegate.page):
    path = "/developers/more-like-this"

    def GET(self):
        return render_template("more_like_this", build_context())


def setup():
    pass
