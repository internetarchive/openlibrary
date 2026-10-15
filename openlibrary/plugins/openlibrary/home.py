"""Controller for home page."""

import logging
import random

import web

from infogami import config  # noqa: F401 side effects may be needed
from infogami.utils import delegate
from infogami.utils.view import render_template
from openlibrary.core import admin, cache, env
from openlibrary.core.carousels import get_carousel_data
from openlibrary.core.helpers import commify
from openlibrary.i18n import gettext as _
from openlibrary.plugins.upstream.utils import (
    convert_iso_to_marc,
    get_blog_feeds,
    get_populated_languages,
)
from openlibrary.plugins.worksearch import search, subjects
from openlibrary.utils import dateutil
from openlibrary.utils.request_context import caching_prethread, req_context

logger = logging.getLogger("openlibrary.home")


def get_homepage(devmode):
    try:
        # Two windows: the card's 28 days and the 28 before, for the change figure.
        stats = admin.get_stats(ndays=2 * LIBRARY_STATS_DAYS, use_mock_data=devmode)
    except Exception:
        logger.error("Error in getting stats", exc_info=True)
        stats = None
    blog_posts = get_blog_feeds()
    featured_subjects = get_cached_featured_subjects()

    # render template should be setting ctx.cssfile
    # but because get_homepage is cached, this doesn't happen
    # during subsequent called
    carousel_data = get_carousel_data()
    page = render_template(
        "home/index",
        stats=stats,
        blog_posts=blog_posts,
        featured_subjects=featured_subjects,
        carousel_data=carousel_data,
        library_stats=get_library_stats(stats),
    )
    # Convert to a dict so it can be cached
    return dict(page)


# The "Around the library" card (home/library_row.html.jinja): four of admin.get_stats's series,
# each summed over the last 28 days, with a sparkline of the 7-day average drawn in a 120x28 box
# and the change in the daily average from the 28 days before.
LIBRARY_STATS_DAYS = 28
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


def percent_change(current: list[int], previous: list[int], min_days: int = 7) -> int | None:
    """Change in the daily average between two windows, counting only days with a count.
    None when either window has fewer than `min_days` of them to go on."""
    current, previous = [v for v in current if v], [v for v in previous if v]
    if len(current) < min_days or len(previous) < min_days:
        return None
    before = sum(previous) / len(previous)
    return round((sum(current) / len(current) - before) / before * 100)


def get_library_stats(stats) -> list[dict]:
    """The card's metrics, in reading order. A series with nothing in the window (visitors, when
    graphite can't be reached) is left off rather than shown as zero."""
    if not stats:
        return []
    series = [
        ("visitors", _("Unique Visitors"), "//archive.org/stats"),
        ("members", _("New Members"), "/stats"),
        ("loans", _("Books Read"), "/subjects/in_library#ebooks=true"),
        ("human_edits", _("Catalog Edits"), "/recentchanges"),
    ]
    metrics = []
    for key, label, href in series:
        # Graphite reports days it has no data for (often today) as None or 0.
        counts = [int(count or 0) for _day, count in stats[key].get_counts(2 * LIBRARY_STATS_DAYS)]
        current, previous = counts[-LIBRARY_STATS_DAYS:], counts[:-LIBRARY_STATS_DAYS]
        if total := sum(current):
            metrics.append(
                {
                    "label": label,
                    "value": compact_number(total),
                    "href": href,
                    "points": sparkline_points(rolling_average(counts)[-LIBRARY_STATS_DAYS:]),
                    "change": percent_change(current, previous),
                }
            )
    return metrics


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


def setup():
    pass
