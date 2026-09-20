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
"""

import logging
import random
from dataclasses import dataclass, field

import web

from infogami.utils import delegate
from infogami.utils.view import render_template
from openlibrary import accounts
from openlibrary.core.bookshelves import Bookshelves
from openlibrary.plugins.worksearch.code import run_solr_query
from openlibrary.plugins.worksearch.schemes.works import WorkSearchScheme

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
    # Set when the sample came back empty, so the page can say why rather than
    # rendering nothing. Local dev indexes are small and often lack the
    # trending/readinglog data the non-default methods sort on.
    message: str = ""


def _label(choices: tuple[Choice, ...], choice_id: str) -> str:
    return next(choice.label for choice in choices if choice.id == choice_id)


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


def _sample(count: int, method: str, pool_query: str) -> list[Row]:
    response = run_solr_query(
        WorkSearchScheme(),
        {"q": pool_query},
        rows=count,
        sort=_sample_sort(method),
        fields=[
            "key",
            "title",
            "author_name",
            "first_publish_year",
            "cover_i",
            "subject",
        ],
        facet=False,
        spellcheck_count=0,
        request_label="MORE_LIKE_THIS_SAMPLE",
    )

    rows = []
    for doc in response.docs:
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


def build_context() -> Context:
    params = web.input(count=str(DEFAULT_COUNT), method="random", pool="all", go="")

    try:
        count = int(params.count)
    except ValueError:
        count = DEFAULT_COUNT
    count = count if count in COUNT_CHOICES else DEFAULT_COUNT

    method = params.method if params.method in {choice.id for choice in METHODS} else "random"
    pool = params.pool if params.pool in {choice.id for choice in POOLS} else "all"

    context = Context(count=count, method=method, pool=pool)
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
    return context


class more_like_this(delegate.page):
    path = "/developers/more-like-this"

    def GET(self):
        return render_template("more_like_this", build_context())


def setup():
    pass
