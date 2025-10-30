"""Controller for home page."""

import logging
import random

import web

from infogami import config  # noqa: F401 side effects may be needed
from infogami.infobase.client import storify
from infogami.utils import delegate
from infogami.utils.view import public, render_template
from openlibrary import accounts
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


def get_continue_reading_books(limit=20):
    """
    Get books for the 'Continue Reading' carousel.
    Returns active loans + recent loan history (up to `limit` total books).

    Args:
        limit: Maximum number of books to return

    Returns:
        list: List of book editions to display in carousel
        None: If user is not logged in or has no reading history
    """
    user = accounts.get_current_user()

    if not user:
        return None

    books = []

    # 1. Get active loans (priority)
    try:
        active_loans = lending.get_loans_of_user(user.key)
        for loan in active_loans:
            if book := web.ctx.site.get(loan['book']):
                book.loan = loan  # Attach loan data
                book.is_active_loan = True
                books.append(book)
    except Exception as e:
        logger.error(
            f"Error fetching active loans for continue reading: {e}", exc_info=True
        )

    # 2. Get recent loan history to fill remaining slots
    if (remaining_slots := limit - len(books)) > 0:
        try:
            from openlibrary.plugins.upstream.account import (
                MyBooksTemplate,
                get_loan_history_data,
            )

            username = user['key'].split('/')[-1]
            mb = MyBooksTemplate(username, key='loan_history')
            history_data = get_loan_history_data(page=1, mb=mb)

            # Filter out books already in active loans
            active_loan_keys = {book.key for book in books}

            for doc in history_data.get('docs', [])[:remaining_slots]:
                if hasattr(doc, 'key') and doc.key not in active_loan_keys:
                    doc.is_active_loan = False
                    books.append(doc)
                elif (
                    isinstance(doc, dict)
                    and doc.get('key')
                    and doc['key'] not in active_loan_keys
                    and (book_obj := web.ctx.site.get(doc['key']))
                ):
                    book_obj.is_active_loan = False
                    books.append(book_obj)

>>>>>>> a9e3889f9 (resolved ruff linting errors)
        except Exception as e:
            logger.error(
                f"Error fetching loan history for continue reading: {e}", exc_info=True
            )

    return books[:limit] if books else None


def get_homepage(devmode):
    try:
        stats = admin.get_stats(use_mock_data=devmode)
    except Exception:
        logger.error("Error in getting stats", exc_info=True)
        stats = None
    blog_posts = get_blog_feeds()

    # Get continue reading books for logged-in users
    try:
        continue_reading = get_continue_reading_books(limit=20)
    except Exception as e:
        logger.error(f"Error fetching continue reading books: {e}", exc_info=True)
        continue_reading = None

    # render template should be setting ctx.cssfile
    # but because get_homepage is cached, this doesn't happen
    # during subsequent called
    page = render_template(
        "home/index",
        stats=stats,
        blog_posts=blog_posts,
        continue_reading=continue_reading,
    )
    # Convert to a dict so it can be cached
    return dict(page)


def get_cached_homepage():
    from openlibrary.plugins.openlibrary.code import is_bot

    five_minutes = 5 * dateutil.MINUTE_SECS
    lang = web.ctx.lang

    # Create user-specific cache key for logged-in users
    if user := accounts.get_current_user():
        # User-specific cache (shorter duration for personalized content)
        key = f'home.homepage.{lang}.user.{user.key}'
        timeout = dateutil.MINUTE_SECS  # 1 minute cache for logged-in users
    else:
        # Public cache (longer duration)
        key = f'home.homepage.{lang}'
        timeout = five_minutes

    cookies = web.cookies()
    if cookies.get('pd', False):
        key += '.pd'
    if cookies.get('sfw', ''):
        key += '.sfw'
    if is_bot():
        key += '.bot'

    mc = cache.memcache_memoize(
        get_homepage, key, timeout=timeout, prethread=caching_prethread()
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
    from openlibrary.plugins.openlibrary.code import is_bot

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
    safe_mode=True,
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
