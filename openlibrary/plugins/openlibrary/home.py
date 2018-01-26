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
from openlibrary.plugins.worksearch import search, subjects
from openlibrary.plugins.openlibrary import lists


logger = logging.getLogger("openlibrary.home")

CAROUSELS_PRESETS = {
    'preset:thrillers': '(creator:"Clancy, Tom" OR creator:"King, Stephen" OR creator:"Clive Cussler" OR creator:("Cussler, Clive") OR creator:("Dean Koontz") OR creator:("Koontz, Dean") OR creator:("Higgins, Jack")) AND !publisher:"Pleasantville, N.Y. : Reader\'s Digest Association" AND languageSorter:"English"',
    'preset:children': '(creator:("parish, Peggy") OR creator:("avi") OR title:("goosebumps") OR creator:("Dahl, Roald") OR creator:("ahlberg, allan") OR creator:("Seuss, Dr") OR creator:("Carle, Eric") OR creator:("Pilkey, Dav"))',
    'preset:comics': '(subject:"comics" OR creator:("Gary Larson") OR creator:("Larson, Gary") OR creator:("Charles M Schulz") OR creator:("Schulz, Charles M") OR creator:("Jim Davis") OR creator:("Davis, Jim") OR creator:("Bill Watterson") OR creator:("Watterson, Bill") OR creator:("Lee, Stan"))',
    'preset:authorsalliance_mitpress': '(openlibrary_subject:(authorsalliance) OR collection:(mitpress) OR publisher:(MIT Press) OR openlibrary_subject:(mitpress)) AND (!loans__status__status:UNAVAILABLE)'
}

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
        page.v2 = True
        return page

class random_book(delegate.page):
    path = "/random"

    def GET(self):
        olid = lending.get_random_available_ia_edition()
        if olid:
            raise web.seeother('/books/%s' % olid)
        raise web.seeother("/")


def get_ia_carousel_books(query=None, subject=None, work_id=None, sorts=None,
                          _type=None, limit=None):
    if 'env' not in web.ctx:
        delegate.fakeload()

    elif query in CAROUSELS_PRESETS:
        query = CAROUSELS_PRESETS[query]

    limit = limit or lending.DEFAULT_IA_RESULTS
    books = lending.get_available(limit=limit, subject=subject, work_id=work_id,
                                  _type=_type, sorts=sorts, query=query)
    formatted_books = [format_book_data(book) for book in books if book != 'error']
    return formatted_books

def get_featured_subjects():
    # web.ctx must be initialized as it won't be available to the background thread.
    if 'env' not in web.ctx:
        delegate.fakeload()

    FEATURED_SUBJECTS = [
        'art', 'science_fiction', 'fantasy', 'biographies', 'recipes',
        'romance', 'textbooks', 'children', 'history', 'medicine', 'religion',
        'mystery_and_detective_stories', 'plays', 'music', 'science'
    ]
    return dict([(subject_name, subjects.get_subject('/subjects/' + subject_name, sort='edition_count'))
                 for subject_name in FEATURED_SUBJECTS])

@public
def get_cached_featured_subjects():
    return cache.memcache_memoize(
        get_featured_subjects, "home.featured_subjects", timeout=cache.HOUR)()


@public
def generic_carousel(query=None, subject=None, work_id=None, _type=None,
                     sorts=None, limit=None, timeout=None):
    memcache_key = 'home.ia_carousel_books'
    cached_ia_carousel_books = cache.memcache_memoize(
        get_ia_carousel_books, memcache_key, timeout=timeout or cache.DEFAULT_CACHE_LIFETIME)
    books = cached_ia_carousel_books(
        query=query, subject=subject, work_id=work_id, _type=_type,
        sorts=sorts, limit=limit)
    return storify(books)

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
    solr = search.get_solr()
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
