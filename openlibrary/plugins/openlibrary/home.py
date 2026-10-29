"""Controller for home page."""

import logging
import random

import web

from infogami import config  # noqa: F401 side effects may be needed
from infogami.utils import delegate
from infogami.utils.view import render_template
from openlibrary.core import admin, cache, env
from openlibrary.core.helpers import commify
from openlibrary.i18n import gettext as _
from openlibrary.plugins.openlibrary import home_genres
from openlibrary.plugins.upstream.utils import (
    convert_iso_to_marc,
    get_blog_feeds,
    get_populated_languages,
)
from openlibrary.plugins.worksearch import search, subjects
from openlibrary.plugins.worksearch.code import work_search_async
from openlibrary.utils import dateutil
from openlibrary.utils.async_utils import async_bridge
from openlibrary.utils.request_context import caching_prethread, get_request_lang, req_context

logger = logging.getLogger("openlibrary.home")


def get_homepage(devmode):
    try:
        stats = admin.get_stats(ndays=LIBRARY_STATS_WINDOW, use_mock_data=devmode)
    except Exception:
        logger.error("Error in getting stats", exc_info=True)
        stats = None
    blog_posts = get_blog_feeds()
    # The genre cache is shared across languages, so names are translated and thin rows dropped per page.
    try:
        marc = home_genres.language_marc(get_request_lang())
        featured_genres = [
            {
                **genre,
                "name": home_genres.display_name(genre),
                "subgenres": [{**s, "name": home_genres.subgenre_name(s)} for s in home_genres.subgenres_for(genre, marc)],
            }
            for genre in get_cached_featured_genres()
        ]
    except Exception:
        logger.error("Error in getting featured genres", exc_info=True)
        featured_genres = []

    # render template should be setting ctx.cssfile
    # but because get_homepage is cached, this doesn't happen
    # during subsequent called
    page = render_template(
        "home/index",
        blog_posts=blog_posts,
        featured_genres=featured_genres,
        library_stats=get_library_stats(stats),
    )
    # Convert to a dict so it can be cached
    return dict(page)


# The stats card (home/library_row.html.jinja): four of admin.get_stats's series,
# each summed over the last 28 days, with a sparkline of the 7-day average drawn in a 120x28 box
# and the change from its first point to its last.
LIBRARY_STATS_DAYS = 28
SMOOTHING_DAYS = 7
# The card's 28 days, plus the six before them so its first day has a full 7-day average.
LIBRARY_STATS_WINDOW = LIBRARY_STATS_DAYS + SMOOTHING_DAYS - 1
SPARKLINE_WIDTH = 120
SPARKLINE_HEIGHT = 28


def compact_number(n: int) -> str:
    """1234 -> "1.2K", 96400 -> "96K", 1200000 -> "1.2M"; under a thousand, the number itself."""
    for threshold, suffix in ((1_000_000, "M"), (1_000, "K")):
        if n >= threshold:
            value = n / threshold
            text = f"{value:.1f}" if value < 10 else f"{value:.0f}"
            if "." in text:
                text = text.rstrip("0").rstrip(".")
            return text + suffix
    return commify(n)


def rolling_average(values: list[int], window: int = 7) -> list[float]:
    """Trailing average of each day and the `window - 1` before it, which irons out the weekend
    dip so the line shows the trend. Zeros are days with no count: left out of each average,
    and a day whose whole window is empty stays 0."""
    averages = []
    for i in range(len(values)):
        days = [v for v in values[max(0, i - window + 1) : i + 1] if v]
        averages.append(sum(days) / len(days) if days else 0)
    return averages


def sparkline_points(values: list[float], width: int = SPARKLINE_WIDTH, height: int = SPARKLINE_HEIGHT, pad: int = 2, min_span: float = 0.12) -> str:
    """SVG polyline points for the daily values, oldest first. The scale tops out at the peak and
    spans at least `min_span` of it, so a rise of 12% or more fills the box and a percent or two stays a ripple.
    Zeros are days with no count and are skipped, not drawn."""
    present = [v for v in values if v]
    if not present:
        return ""
    high = max(present)
    low = min(*present, high * (1 - min_span))
    step = (width - 2 * pad) / max(len(values) - 1, 1)
    return " ".join(f"{pad + i * step:.1f},{pad + (height - 2 * pad) * (high - value) / (high - low):.1f}" for i, value in enumerate(values) if value)


def percent_change(line: list[float]) -> int | None:
    """Change from the first point of the sparkline to its last: the 7-day average at the start of
    the window against the one ending today, so the figure always agrees with the line."""
    present = [v for v in line if v]
    if len(present) < 2:
        return None
    return round((present[-1] - present[0]) / present[0] * 100)


def get_library_stats(stats) -> list[dict]:
    """The card's metrics, in reading order. A series with nothing in the window is left off
    rather than shown as zero."""
    if not stats:
        return []

    def metric(key, label, href):
        # A count the stats script began writing part-way through the window would add up to a fraction of a month.
        if not (stat := stats.get(key)) or not stat.has_counts(LIBRARY_STATS_WINDOW):
            return None
        # Graphite reports days it has no data for (often today) as None or 0.
        counts = [int(count or 0) for _day, count in stat.get_counts(LIBRARY_STATS_WINDOW)]
        line = rolling_average(counts, SMOOTHING_DAYS)[-LIBRARY_STATS_DAYS:]
        if total := sum(counts[-LIBRARY_STATS_DAYS:]):
            return {
                "label": label,
                "value": compact_number(total),
                "href": href,
                "points": sparkline_points(line),
                "change": percent_change(line),
            }
        return None

    series = [
        metric("members", _("New Members"), "/stats"),
        metric("loans", _("Books Read"), "/subjects/in_library#ebooks=true"),
        # Catalog edits (human edits minus signups) and list edits are newer daily counts. Until the
        # docs carry a full window of them, the older series stand in, so the card never sums or
        # compares across the change.
        metric("catalog_edits", _("Catalog Edits"), "/recentchanges") or metric("human_edits", _("Catalog Edits"), "/recentchanges"),
        metric("list_edits", _("Lists Updated"), "/lists") or metric("lists", _("Lists Created"), "/lists"),
    ]
    return [m for m in series if m]


def get_cached_homepage():
    from openlibrary.plugins.openlibrary.code import is_bot

    five_minutes = 5 * dateutil.MINUTE_SECS
    lang = web.ctx.lang
    key = f"home.homepage.{lang}"
    ctx = req_context.get()
    if ctx.print_disabled:
        key += ".pd"
    if ctx.sfw:
        key += ".sfw"
    if is_bot():
        key += ".bot"

    mc = cache.memcache_memoize(get_homepage, key, timeout=five_minutes, prethread=caching_prethread())
    devmode = env.get_ol_env().LOCAL_DEV
    page = mc(devmode)

    if not page:
        mc.memcache_delete_by_args(devmode)
        mc(devmode)

    return page


class home(delegate.page):
    path = "/"

    def GET(self):
        if devmode := env.get_ol_env().LOCAL_DEV:
            homepage_data = get_homepage(devmode)
        else:
            homepage_data = get_cached_homepage()

        # when homepage is cached, home/index.html template
        # doesn't run ctx.setdefault to set the cssfile so we must do so here:
        web.template.Template.globals["ctx"]["cssfile"] = "home"
        return web.template.TemplateResult(homepage_data)


@cache.memoize(
    engine="memcache",
    key=lambda count, language=None: f"home.random_book.{language or 'all'}",
    expires=dateutil.HALF_HOUR_SECS,
)
def get_random_borrowable_ebook_keys(count: int, language: str | None = None) -> list[str]:
    solr = search.get_solr()
    query = "type:edition AND ebook_access:[borrowable TO *]"
    if language:
        query += f" AND language:{language}"
    docs = solr.select(
        query,
        fields=["key"],
        rows=count,
        sort=f"random_{random.random()} desc",
    )["docs"]
    return [doc["key"] for doc in docs]


class random_book(delegate.page):
    path = "/random"

    def GET(self):
        # Get user's language preference
        user_lang = None
        web_lang = web.ctx.lang or "en"
        marc_lang = convert_iso_to_marc(web_lang)

        # Only filter by language if it's a populated language
        if marc_lang and marc_lang in get_populated_languages():
            user_lang = marc_lang

        keys = get_random_borrowable_ebook_keys(1000, language=user_lang)
        raise web.seeother(random.choice(keys))


def get_featured_subjects():
    """The subject list behind the OPDS catalog's navigation (api.py)."""
    # web.ctx must be initialized as it won't be available to the background thread.
    if "env" not in web.ctx:
        delegate.fakeload()

    FEATURED_SUBJECTS = [
        {
            "key": "/subjects/art",
            "presentable_name": _("Art"),
            "emoji": "🎨",
        },
        {
            "key": "/subjects/science_fiction",
            "presentable_name": _("Science Fiction"),
            "emoji": "👽",
        },
        {
            "key": "/subjects/fantasy",
            "presentable_name": _("Fantasy"),
            "emoji": "🧙‍♂️",
        },
        {
            "key": "/subjects/biographies",
            "presentable_name": _("Biographies"),
            "emoji": "📖",
        },
        {
            "key": "/subjects/recipes",
            "presentable_name": _("Recipes"),
            "emoji": "🍳",
        },
        {
            "key": "/subjects/romance",
            "presentable_name": _("Romance"),
            "emoji": "❤️",
        },
        {
            "key": "/subjects/textbooks",
            "presentable_name": _("Textbooks"),
            "emoji": "📚",
        },
        {
            "key": "/subjects/children",
            "presentable_name": _("Children"),
            "emoji": "👶",
        },
        {
            "key": "/subjects/history",
            "presentable_name": _("History"),
            "emoji": "📜",
        },
        {
            "key": "/subjects/medicine",
            "presentable_name": _("Medicine"),
            "emoji": "💊",
        },
        {
            "key": "/subjects/religion",
            "presentable_name": _("Religion"),
            "emoji": "✝️",
        },
        {
            "key": "/subjects/mystery_and_detective_stories",
            "presentable_name": _("Mystery and Detective Stories"),
            "emoji": "🕵️‍♂️",
        },
        {
            "key": "/subjects/plays",
            "presentable_name": _("Plays"),
            "emoji": "🎭",
        },
        {
            "key": "/subjects/music",
            "presentable_name": _("Music"),
            "emoji": "🎶",
        },
        {
            "key": "/subjects/science",
            "presentable_name": _("Science"),
            "emoji": "🔬",
        },
    ]
    return [{**subject, **(subjects.get_subject(subject["key"], limit=0) or {})} for subject in FEATURED_SUBJECTS]


def get_cached_featured_subjects():
    return cache.memcache_memoize(
        get_featured_subjects,
        f"home.featured_subjects.{web.ctx.lang}",
        timeout=dateutil.HOUR_SECS,
        prethread=caching_prethread(),
    )()


GENRE_TILE_COVERS = 3


def get_featured_tile_covers() -> list[int]:
    """Covers for the Featured tile: its Trending row, live, unlike the other tiles' hand-picked ones."""
    results = async_bridge.run(
        work_search_async(
            {"q": home_genres.solr_query(home_genres.FEATURED), "has_fulltext": "true"},
            sort="trending",
            fields="cover_i",
            limit=GENRE_TILE_COVERS * 2,
            facet=False,
            request_label="BOOK_CAROUSEL",
        )
    )
    return [doc["cover_i"] for doc in results.get("docs", []) if doc.get("cover_i")][:GENRE_TILE_COVERS]


def get_featured_genres():
    """Tiles for home/browse_stacks.html.jinja, Featured first. A genre without picked covers gets no tile."""
    if "env" not in web.ctx:
        delegate.fakeload()
    picked = home_genres.load_tile_covers()
    # Fall back to the picked Featured covers when the live query is empty (Solr error, or a dev index with no trending data).
    picked = {**picked, home_genres.FEATURED["slug"]: get_featured_tile_covers() or picked.get(home_genres.FEATURED["slug"], [])}
    nodes = [home_genres.FEATURED, *(genre for genre in home_genres.load_home_genres() if picked.get(genre["slug"]))]
    return [{**genre, "covers": picked[genre["slug"]][:GENRE_TILE_COVERS]} for genre in nodes]


def get_cached_featured_genres():
    return cache.memcache_memoize(
        get_featured_genres,
        "home.featured_genres",
        timeout=dateutil.DAY_SECS,
        prethread=caching_prethread(),
    )()


def setup():
    pass
