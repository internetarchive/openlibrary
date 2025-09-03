"""Controller for home page."""

import logging
import random

import web

from infogami import config  # noqa: F401 side effects may be needed
from infogami.infobase.client import storify
from infogami.utils import delegate
from infogami.utils.view import public, render_template
from openlibrary.core import admin, cache, ia, lending
from openlibrary.i18n import gettext as _
from openlibrary.plugins.upstream.utils import get_blog_feeds
from openlibrary.plugins.worksearch import search, subjects
from openlibrary.utils import dateutil

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
    from openlibrary.plugins.openlibrary.code import is_bot  # noqa: PLC0415

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
    page = mc(devmode=("dev" in web.ctx.features))

    if not page:
        mc.memcache_delete_by_args()
        mc()

    return page


# Because of caching, memcache will call `get_homepage` on another thread! So we
# need a way to carry some information to that computation on the other thread.
# We do that by using a python closure. The outer function is executed on the main
# thread, so all the web.* stuff is correct. The inner function is executed on the
# other thread, so all the web.* stuff will be dummy.
def caching_prethread():
    from openlibrary.plugins.openlibrary.code import is_bot  # noqa: PLC0415

    # web.ctx.lang is undefined on the new thread, so need to transfer it over
    lang = web.ctx.lang
    _is_bot = is_bot()

    def main():
        # Leaving this in since this is a bit strange, but you can see it clearly
        # in action with this debug line:
        # web.debug(f'XXXXXXXXXXX web.ctx.lang={web.ctx.get("lang")}; {lang=}')
        delegate.fakeload()
        web.ctx.lang = lang
        web.ctx.is_bot = _is_bot

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
    engine="memcache", key="home.random_book", expires=dateutil.HALF_HOUR_SECS
)
def get_random_borrowable_ebook_keys(count: int) -> list[str]:
    solr = search.get_solr()
    docs = solr.select(
        'type:edition AND ebook_access:[borrowable TO *]',
        fields=['key'],
        rows=count,
        sort=f'random_{random.random()} desc',
    )['docs']
    return [doc['key'] for doc in docs]


class random_book(delegate.page):
    path = "/random"

    def GET(self):
        keys = get_random_borrowable_ebook_keys(1000)
        raise web.seeother(random.choice(keys))


def get_ia_carousel_books(query=None, subject=None, sorts=None, limit=None):
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
        {'key': '/subjects/art', 'presentable_name': _('Art')},
        {'key': '/subjects/science_fiction', 'presentable_name': _('Science Fiction')},
        {'key': '/subjects/fantasy', 'presentable_name': _('Fantasy')},
        {'key': '/subjects/biographies', 'presentable_name': _('Biographies')},
        {'key': '/subjects/recipes', 'presentable_name': _('Recipes')},
        {'key': '/subjects/romance', 'presentable_name': _('Romance')},
        {'key': '/subjects/textbooks', 'presentable_name': _('Textbooks')},
        {'key': '/subjects/children', 'presentable_name': _('Children')},
        {'key': '/subjects/history', 'presentable_name': _('History')},
        {'key': '/subjects/medicine', 'presentable_name': _('Medicine')},
        {'key': '/subjects/religion', 'presentable_name': _('Religion')},
        {
            'key': '/subjects/mystery_and_detective_stories',
            'presentable_name': _('Mystery and Detective Stories'),
        },
        {'key': '/subjects/plays', 'presentable_name': _('Plays')},
        {'key': '/subjects/music', 'presentable_name': _('Music')},
        {'key': '/subjects/science', 'presentable_name': _('Science')},
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
):
    memcache_key = 'home.ia_carousel_books'
    cached_ia_carousel_books = cache.memcache_memoize(
        get_ia_carousel_books,
        memcache_key,
        timeout=timeout or cache.DEFAULT_CACHE_LIFETIME,
    )
    books = cached_ia_carousel_books(
        query=query,
        subject=subject,
        sorts=sorts,
        limit=limit,
    )
    if not books:
        books = cached_ia_carousel_books.update(
            query=query,
            subject=subject,
            sorts=sorts,
            limit=limit,
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
    d.authors = get_authors(work if work else book)
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


def setup():
    pass
