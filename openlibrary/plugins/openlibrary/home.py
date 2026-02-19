"""Controller for home page."""

import logging
import random

import httpx
import web

from infogami import config  # noqa: F401 side effects may be needed
from infogami.infobase.client import storify
from infogami.utils import delegate
from infogami.utils.view import public, render_template
from openlibrary.core import admin, cache, ia, lending
from openlibrary.i18n import gettext as _
from openlibrary.plugins.upstream.utils import (
    convert_iso_to_marc,
    get_blog_feeds,
    get_populated_languages,
)
from openlibrary.plugins.worksearch import search, subjects
from openlibrary.utils import dateutil
from openlibrary.utils.request_context import (
    req_context,
    set_context_from_legacy_web_py,
)

logger = logging.getLogger("openlibrary.home")

CAROUSELS_PRESETS = {
    'preset:comics': (
        '(subject:"comics" OR creator:("Gary Larson") OR creator:("Larson, Gary") '
        'OR creator:("Charles M Schulz") OR creator:("Schulz, Charles M") OR '
        'creator:("Jim Davis") OR creator:("Davis, Jim") OR creator:("Bill Watterson")'
        'OR creator:("Watterson, Bill") OR creator:("Lee, Stan"))'
    ),
    'preset:authorsalliance_mitpress': (
        '(openlibrary_subject:(authorsalliance) OR collection:(mitpress) OR '
        'publisher:(MIT Press) OR openlibrary_subject:(mitpress))'
    ),
}


def get_homepage(devmode):
    try:
        stats = admin.get_stats(use_mock_data=devmode)
    except Exception:
        logger.error("Error in getting stats", exc_info=True)
        stats = None
    blog_posts = get_blog_feeds()

    # render template should be setting ctx.cssfile
    # but because get_homepage is cached, this doesn't happen
    # during subsequent called
    page = render_template("home/index", stats=stats, blog_posts=blog_posts)
    # Convert to a dict so it can be cached
    return dict(page)


def get_cached_homepage():
    from openlibrary.plugins.openlibrary.code import is_bot

    five_minutes = 5 * dateutil.MINUTE_SECS
    lang = web.ctx.lang
    key = f'home.homepage.{lang}'
    cookies = web.cookies()
    if cookies.get('pd', False):
        key += '.pd'
    if cookies.get('sfw', ''):
        key += '.sfw'
    if is_bot():
        key += '.bot'

    mc = cache.memcache_memoize(
        get_homepage, key, timeout=five_minutes, prethread=caching_prethread()
    )
    devmode = "dev" in web.ctx.features
    page = mc(devmode)

    if not page:
        mc.memcache_delete_by_args(devmode)
        mc(devmode)

    return page


# Because of caching, memcache will call `get_homepage` on another thread! So we
# need a way to carry some information to that computation on the other thread.
# We do that by using a python closure. The outer function is executed on the main
# thread, so all the web.* stuff is correct. The inner function is executed on the
# other thread, so all the web.* stuff will be dummy.
def caching_prethread():
    from openlibrary.plugins.openlibrary.code import is_bot

    # web.ctx.lang is undefined on the new thread, so need to transfer it over
    lang = req_context.get().lang
    host = web.ctx.host
    _is_bot = is_bot()

    def main():
        # Leaving this in since this is a bit strange, but you can see it clearly
        # in action with this debug line:
        # web.debug(f'XXXXXXXXXXX web.ctx.lang={web.ctx.get("lang")}; {lang=}')
        delegate.fakeload()
        web.ctx.lang = lang
        web.ctx.is_bot = _is_bot
        web.ctx.host = host
        set_context_from_legacy_web_py()

    return main


class home(delegate.page):
    path = "/"

    def GET(self):
        cached_homepage = get_cached_homepage()
        # when homepage is cached, home/index.html template
        # doesn't run ctx.setdefault to set the cssfile so we must do so here:
        web.template.Template.globals['ctx']['cssfile'] = 'home'
        return web.template.TemplateResult(cached_homepage)


@cache.memoize(
    engine="memcache",
    key=lambda count, language=None: f"home.random_book.{language or 'all'}",
    expires=dateutil.HALF_HOUR_SECS,
)
def get_random_borrowable_ebook_keys(
    count: int, language: str | None = None
) -> list[str]:
    solr = search.get_solr()
    query = 'type:edition AND ebook_access:[borrowable TO *]'
    if language:
        query += f' AND language:{language}'
    docs = solr.select(
        query,
        fields=['key'],
        rows=count,
        sort=f'random_{random.random()} desc',
    )['docs']
    return [doc['key'] for doc in docs]


class random_book(delegate.page):
    path = "/random"

    def GET(self):
        # Get user's language preference
        user_lang = None
        web_lang = web.ctx.lang or 'en'
        marc_lang = convert_iso_to_marc(web_lang)

        # Only filter by language if it's a populated language
        if marc_lang and marc_lang in get_populated_languages():
            user_lang = marc_lang

        keys = get_random_borrowable_ebook_keys(1000, language=user_lang)
        raise web.seeother(random.choice(keys))


def get_ia_carousel_books(
    query=None, subject=None, sorts=None, limit=None, safe_mode=True
):
    if 'env' not in web.ctx:
        delegate.fakeload()

    elif query in CAROUSELS_PRESETS:
        query = CAROUSELS_PRESETS[query]

    limit = limit or lending.DEFAULT_IA_RESULTS
    books = lending.get_available(
        limit=limit,
        subject=subject,
        sorts=sorts,
        query=query,
        safe_mode=safe_mode,
    )
    formatted_books = [
        format_book_data(book, False) for book in books if book != 'error'
    ]
    return formatted_books


def get_featured_subjects():
    # web.ctx must be initialized as it won't be available to the background thread.
    if 'env' not in web.ctx:
        delegate.fakeload()

    FEATURED_SUBJECTS = [
        {
            'key': '/subjects/art',
            'presentable_name': _('Art'),
            'emoji': '🎨',
        },
        {
            'key': '/subjects/science_fiction',
            'presentable_name': _('Science Fiction'),
            'emoji': '👽',
        },
        {
            'key': '/subjects/fantasy',
            'presentable_name': _('Fantasy'),
            'emoji': '🧙‍♂️',
        },
        {
            'key': '/subjects/biographies',
            'presentable_name': _('Biographies'),
            'emoji': '📖',
        },
        {
            'key': '/subjects/recipes',
            'presentable_name': _('Recipes'),
            'emoji': '🍳',
        },
        {
            'key': '/subjects/romance',
            'presentable_name': _('Romance'),
            'emoji': '❤️',
        },
        {
            'key': '/subjects/textbooks',
            'presentable_name': _('Textbooks'),
            'emoji': '📚',
        },
        {
            'key': '/subjects/children',
            'presentable_name': _('Children'),
            'emoji': '👶',
        },
        {
            'key': '/subjects/history',
            'presentable_name': _('History'),
            'emoji': '📜',
        },
        {
            'key': '/subjects/medicine',
            'presentable_name': _('Medicine'),
            'emoji': '💊',
        },
        {
            'key': '/subjects/religion',
            'presentable_name': _('Religion'),
            'emoji': '✝️',
        },
        {
            'key': '/subjects/mystery_and_detective_stories',
            'presentable_name': _('Mystery and Detective Stories'),
            'emoji': '🕵️‍♂️',
        },
        {
            'key': '/subjects/plays',
            'presentable_name': _('Plays'),
            'emoji': '🎭',
        },
        {
            'key': '/subjects/music',
            'presentable_name': _('Music'),
            'emoji': '🎶',
        },
        {
            'key': '/subjects/science',
            'presentable_name': _('Science'),
            'emoji': '🔬',
        },
    ]
    return [
        {**subject, **(subjects.get_subject(subject['key'], limit=0) or {})}
        for subject in FEATURED_SUBJECTS
    ]


@public
def get_cached_featured_subjects():
    return cache.memcache_memoize(
        get_featured_subjects,
        f"home.featured_subjects.{web.ctx.lang}",
        timeout=dateutil.HOUR_SECS,
        prethread=caching_prethread(),
    )()


@public
def generic_carousel(
    query=None,
    subject=None,
    sorts=None,
    limit=None,
    timeout=None,
    safe_mode=True,
):
    memcache_key = 'home.ia_carousel_books'
    cached_ia_carousel_books = cache.memcache_memoize(
        get_ia_carousel_books,
        memcache_key,
        timeout=timeout or cache.DEFAULT_CACHE_LIFETIME,
        prethread=caching_prethread(),
    )
    books = cached_ia_carousel_books(
        query=query,
        subject=subject,
        sorts=sorts,
        limit=limit,
        safe_mode=safe_mode,
    )
    if not books:
        books = cached_ia_carousel_books.update(
            query=query,
            subject=subject,
            sorts=sorts,
            limit=limit,
            safe_mode=safe_mode,
        )[0]
    return storify(books) if books else books


def format_book_data(book, fetch_availability=True):
    d = web.storage()
    d.key = book.get('key')
    d.url = book.url()
    d.title = book.title or None
    d.ocaid = book.get("ocaid")
    d.eligibility = book.get("eligibility", {})
    d.availability = book.get('availability', {})

    def get_authors(doc):
        return [web.storage(key=a.key, name=a.name or None) for a in doc.get_authors()]

    work = book.works and book.works[0]
    d.authors = get_authors(work or book)
    d.work_key = work.key if work else book.key

    if cover := book.get_cover():
        d.cover_url = cover.url("M")
    elif d.ocaid:
        d.cover_url = 'https://archive.org/services/img/%s' % d.ocaid

    if fetch_availability and d.ocaid:
        collections = ia.get_metadata(d.ocaid).get('collection', [])

        if 'inlibrary' in collections:
            d.borrow_url = book.url("/borrow")
        else:
            d.read_url = book.url("/borrow")
    return d


BOOK_TALKS_API_URL = "https://archive.org/advancedsearch.php"


def get_book_talks(limit: int = 20) -> list[dict]:
    """Fetch book talks from Internet Archive's booktalks collection.

    Returns a list of dicts with identifier, title, date, cover_url, and video_url.
    """
    if 'env' not in web.ctx:
        delegate.fakeload()

    params = {
        'q': 'collection:booktalks',
        'fl[]': ['identifier', 'title', 'date'],
        'sort[]': 'date desc',
        'rows': limit,
        'page': 1,
        'output': 'json',
    }

    try:
        response = httpx.get(BOOK_TALKS_API_URL, params=params, timeout=10.0)
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, httpx.TimeoutException, ValueError) as e:
        logger.error(f"Error fetching book talks: {e}", exc_info=True)
        return []

    docs = data.get('response', {}).get('docs', [])
    book_talks = []

    for doc in docs:
        identifier = doc.get('identifier')
        if not identifier:
            continue

        book_talk = {
            'identifier': identifier,
            'title': doc.get('title', 'Untitled'),
            'date': doc.get('date', ''),
            'cover_url': f'https://archive.org/services/img/{identifier}',
            'video_url': f'https://archive.org/details/{identifier}',
        }
        book_talks.append(book_talk)

    return book_talks


@public
def get_cached_book_talks(limit: int = 20):
    """Get book talks with 1-day caching."""
    return cache.memcache_memoize(
        get_book_talks,
        "home.book_talks",
        timeout=dateutil.DAY_SECS,
        prethread=caching_prethread(),
    )(limit)


def setup():
    pass
