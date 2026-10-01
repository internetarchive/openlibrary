"""Controller for home page."""

import logging
import random
from urllib.parse import urlencode

import web

from infogami import config  # noqa: F401 side effects may be needed
from infogami.utils import delegate
from infogami.utils.view import render_template
from openlibrary.core import admin, cache, env
from openlibrary.core.carousels import get_carousel_data
from openlibrary.core.helpers import commify
from openlibrary.i18n import gettext as _
from openlibrary.plugins.openlibrary import home_genres
from openlibrary.plugins.upstream.utils import (
    convert_iso_to_marc,
    get_blog_feeds,
    get_populated_languages,
)
from openlibrary.plugins.worksearch import search, subjects
from openlibrary.utils import dateutil
from openlibrary.utils.async_utils import async_bridge
from openlibrary.utils.request_context import caching_prethread, req_context

logger = logging.getLogger("openlibrary.home")


def get_homepage(devmode):
    try:
        stats = admin.get_stats(use_mock_data=devmode)
    except Exception:
        logger.error("Error in getting stats", exc_info=True)
        stats = None
    blog_posts = get_blog_feeds()
    # The template shuffles the tiles per visit, so the cached order doesn't matter.
    featured_genres = get_cached_featured_genres()

    # render template should be setting ctx.cssfile
    # but because get_homepage is cached, this doesn't happen
    # during subsequent called
    carousel_data = get_carousel_data()
    page = render_template(
        "home/index",
        stats=stats,
        blog_posts=blog_posts,
        featured_genres=featured_genres,
        carousel_data=carousel_data,
    )
    # Convert to a dict so it can be cached
    return dict(page)


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
    """The subject list behind the OPDS catalog's navigation (api.py). The home page's
    subject strip that used it is gone; the stacks below replaced it."""
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


# Covers shown fanned on each genre tile.
GENRE_TILE_COVERS = 3


def subject_tile_labels() -> dict[str, str]:
    """Translated names for the subject tiles in home_genres.json (keyed by slug). Genre names
    come from the tags vocabulary and aren't translated yet."""
    return {
        "kids": _("Kids"),
        "history": _("History"),
        "biography": _("Biography"),
        "philosophy": _("Philosophy"),
        "psychology": _("Psychology"),
        "poetry": _("Poetry"),
        "travel": _("Travel"),
        "science": _("Science"),
        "cooking": _("Cooking"),
        "religion": _("Religion"),
        "art": _("Art"),
        "textbooks": _("Textbooks"),
    }


def get_featured_genres():
    """Genre tiles for home/browse_stacks.html.jinja: the vocabulary tree plus live readable counts
    and a few trending covers per genre. One grouped Solr query for all of them, cached for a day."""
    if "env" not in web.ctx:
        delegate.fakeload()
    nodes = home_genres.load_home_genres()
    queries = [home_genres.solr_query(genre) for genre in nodes]
    # One group per genre: its numFound is the readable count, its docs the most trending covers.
    params = [
        ("q", "*:*"),
        ("fq", home_genres.READABLE_CLAUSE),
        ("fq", '-subject:"content_warning:cover"'),
        ("fl", "cover_i"),
        ("rows", 0),
        ("group", "true"),
        ("group.limit", GENRE_TILE_COVERS * 2),
        ("group.sort", "def(trending_z_score,0) desc"),
        ("wt", "json"),
        *(("group.query", query) for query in queries),
    ]
    grouped = async_bridge.run(search.get_solr().raw_request("select", urlencode(params))).json()["grouped"]
    labels = subject_tile_labels()
    genres = []
    for genre, query in zip(nodes, queries, strict=True):
        doclist = grouped[query]["doclist"]
        genres.append(
            {
                **genre,
                "name": labels.get(genre["slug"], genre["name"]) if genre["kind"] == "subject" else genre["name"],
                "readable_count": doclist["numFound"],
                "readable_count_str": commify(doclist["numFound"]),
                "covers": [doc["cover_i"] for doc in doclist["docs"] if doc.get("cover_i")][:GENRE_TILE_COVERS],
                "url": home_genres.browse_url(genre),
            }
        )
    # Nothing readable, no tile. Order is decided at render time.
    return [g for g in genres if g["readable_count"]]


def get_cached_featured_genres():
    return cache.memcache_memoize(
        get_featured_genres,
        "home.featured_genres",
        timeout=dateutil.DAY_SECS,
        prethread=caching_prethread(),
    )()


def setup():
    pass
