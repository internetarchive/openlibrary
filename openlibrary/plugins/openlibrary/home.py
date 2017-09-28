"""Controller for home page.
"""
import random
import web
import simplejson
import logging

from infogami.utils import delegate
from infogami.utils.view import render_template, public
from infogami.infobase.client import storify
from infogami import config

from openlibrary import accounts
from openlibrary.core import admin, cache, ia, inlibrary, lending, \
    helpers as h
from openlibrary.plugins.upstream import borrow
from openlibrary.plugins.upstream.utils import get_blog_feeds
from openlibrary.plugins.worksearch import search
from openlibrary.plugins.openlibrary import lists

DEFAULT_CACHE_LIFETIME = 120  # seconds

logger = logging.getLogger("openlibrary.home")

class home(delegate.page):
    path = "/"

    def is_enabled(self):
        return "lending_v2" in web.ctx.features

    def GET(self):
        try:
            if 'counts_db' in config.admin:
                stats = admin.get_stats()
            else:
                stats = None
        except Exception:
            logger.error("Error in getting stats", exc_info=True)
            stats = None
        blog_posts = get_blog_feeds()
        page = render_template(
            "home/index", stats=stats,
            blog_posts=blog_posts,
        )
        return page


CUSTOM_QUERIES = {}
def get_carousel_by_ia_query(key, usekey=False):
    def render_ia_carousel(query=None, subject=None, sorts=None, limit=None):
        limit = limit or lending.DEFAULT_IA_RESULTS
        books = lending.get_available(limit=limit, subject=subject, sorts=sorts, query=query)
        formatted_books = [format_book_data(book) for book in books if book != 'error']
        return storify(formatted_books)
    memcache_key = None if not usekey else "home.%s" % key
    return cache.memcache_memoize(
        render_ia_carousel, memcache_key, timeout=DEFAULT_CACHE_LIFETIME)

@public
def generic_carousel(key, query=None, subject=None, sorts=None, limit=None):
    if key not in CUSTOM_QUERIES:
        CUSTOM_QUERIES[key] = get_carousel_by_ia_query(key)
    books = CUSTOM_QUERIES[key](query=query, subject=subject, sorts=sorts, limit=limit)
    random.shuffle(books)
    return books

@public
def carousel_from_list(key, randomize=False, limit=60):
    css_id = key.split("/")[-1] + "_carousel"

    data = format_list_editions(key)
    if randomize:
        random.shuffle(data)
    data = data[:limit]
    return render_template(
        "books/carousel", storify(data), id=css_id, pixel="CarouselList")

@public
def loans_carousel(loans=None, cssid="loans_carousel", pixel="CarouselLoans"):
    """Generates 'Your Loans' carousel on home page"""
    if not loans:
        return ''
    books = []
    for loan in loans:
        loan_book = web.ctx.site.get(loan['book'])
        if loan_book:
            books.append(format_book_data(loan_book))
    return render_template(
        'books/carousel', storify(books), id=cssid, pixel=pixel, loans=True
    ) if books else ''

@public
def readonline_carousel():
    """Return template code for books pulled from search engine.
       TODO: If problems, use stock list.
    """
    try:
        data = random_ebooks()
        if len(data) > 60:
            data = random.sample(data, 60)
        return storify(data)

    except Exception:
        logger.error("Failed to compute data for readonline_carousel", exc_info=True)
        return None

def random_ebooks(limit=2000):
    solr = search.get_works_solr()
    sort = "edition_count desc"
    result = solr.select(
        query='has_fulltext:true -public_scan_b:false',
        rows=limit,
        sort=sort,
        fields=[
            'has_fulltext',
            'key',
            'ia',
            "title",
            "cover_edition_key",
            "author_key", "author_name",
        ])

    def process_doc(doc):
        d = {}

        key = doc.get('key', '')
        # New solr stores the key as /works/OLxxxW
        if not key.startswith("/works/"):
            key = "/works/" + key

        d['url'] = key
        d['title'] = doc.get('title', '')

        if 'author_key' in doc and 'author_name' in doc:
            d['authors'] = [{"key": key, "name": name} for key, name in zip(doc['author_key'], doc['author_name'])]

        if 'cover_edition_key' in doc:
            d['cover_url'] = h.get_coverstore_url() + "/b/olid/%s-M.jpg" % doc['cover_edition_key']

        d['read_url'] = "//archive.org/stream/" + doc['ia'][0]
        return d

    return [process_doc(doc) for doc in result.get('docs', []) if doc.get('ia')]

# cache the results of random_ebooks in memcache for 15 minutes
random_ebooks = cache.memcache_memoize(random_ebooks, "home.random_ebooks", timeout=15*60)

def format_list_editions(key):
    """Formats the editions of a list suitable for display in carousel.
    """
    if 'env' not in web.ctx:
        delegate.fakeload()

    seed_list = web.ctx.site.get(key)
    if not seed_list:
        return []

    editions = {}
    for seed in seed_list.seeds:
        if not isinstance(seed, basestring):
            if seed.type.key == "/type/edition":
                editions[seed.key] = seed
            else:
                try:
                    e = pick_best_edition(seed)
                except StopIteration:
                    continue
                editions[e.key] = e
    return [format_book_data(e) for e in editions.values()]

# cache the results of format_list_editions in memcache for 5 minutes
format_list_editions = cache.memcache_memoize(format_list_editions, "home.format_list_editions", timeout=5*60)

def pick_best_edition(work):
    return (e for e in work.editions if e.ocaid).next()

def format_book_data(book):
    d = web.storage()
    d.key = book.get('key')
    d.url = book.url()
    d.title = book.title or None
    d.ocaid = book.get("ocaid")

    def get_authors(doc):
        return [web.storage(key=a.key, name=a.name or None) for a in doc.get_authors()]

    work = book.works and book.works[0]
    d.authors = get_authors(work if work else book)
    cover = work.get_cover() if work and work.get_cover() else book.get_cover()

    if cover:
        d.cover_url = cover.url("M")
    elif d.ocaid:
        d.cover_url = 'https://archive.org/services/img/%s' % d.ocaid

    if d.ocaid:
        collections = ia.get_meta_xml(d.ocaid).get("collection", [])

        if 'lendinglibrary' in collections or 'inlibrary' in collections:
            d.borrow_url = book.url("/borrow")
        else:
            d.read_url = book.url("/borrow")
    return d

def setup():
    pass
