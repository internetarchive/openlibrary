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

from openlibrary.data import popular
from openlibrary import accounts
from openlibrary.core import admin, cache, ia, inlibrary, lending, \
    helpers as h
from openlibrary.plugins.upstream import borrow
from openlibrary.plugins.upstream.utils import get_blog_feeds
from openlibrary.plugins.worksearch import search
from openlibrary.plugins.openlibrary import lists

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

        lending_list = config.get("home", {}).get("lending_list")
        returncart_list = config.get("home", {}).get("returncart_list")

        user = accounts.get_current_user()
        try:
            loans = borrow.get_loans(user) if user else None
        except:
            loans = None

        page = render_template(
            "home/index", stats=stats,
            blog_posts=blog_posts,
            lending_list=lending_list,
            returncart_list=returncart_list,
            user=user, loans=loans,
            popular_books=[],
            waitlisted_books=[],
        )
        page.homepage = True
        return page


@public
def objhas(a, b, default=None):
    return getattr(a, b, default)

@public
def popular_carousel(available_limit=30, waitlist_limit=18, loan_check_batch_size=100):
    """Renders a carousel of popular editions, which are available for
    reading or borrowing, from user lists (borrowable or downloadable;
    excludes daisy only).

    Args:
        available_limit (int) - Load the popular carousel with how
        many items?  (preferably divisible by 6; number of books shown
        per page)

        waitlist_limit (int)) - limit waitlist to how many books

        loan_check_batch_size (int) - Bulk submits this many
        archive.org itemids at a time to see if they are available to
        be borrowed (only considers waitinglist and bookreader
        borrows, no acs4)

    Selected Lists:
        popular.popular is a mapping of OL ids to archive.org identifiers
        for popular book editions coming from the following OL lists:

        /people/mekBot/lists/OL104041L is a manually curated
        collection of popular available books which was constructed by
        looking at goodreads
        (http://www.goodreads.com/list/show/1.Best_Books_Ever) Best
        Ever list. Because this list is more highly curated and has
        more overall recognizable and popular books, we prioritize
        drawing from this list (shuffled) first and then fallback to
        other lists as this one is depleted (i.e. all books become
        unavailable for checking out).

        /people/openlibrary/lists/OL104411L comes from the "top 2000+
        most requested print disabled eBooks in California" displayed
        from the /lists page.

    Popular List Construction:

        https://github.com/internetarchive/openlibrary/pull/406#issuecomment-268090607
        The expensive part about automatically checking the list seeds above
        for availability is there's no apparent easy way to get ocaids for a
        collection of editions at once. Thus, web.ctx.site.get needs be used
        on each Edition (which is expensive) before a batch of editions can
        be checked for availability. If we had the ocaids of list seeds upfront
        and could query them in bulk, this would eliminate the problem.

        As a work-around, we periodically create a flatfile cache of
        the above list.seed keys mapped ahead of time to their ocaids
        (i.e. `popular.popular`).

        For steps on (re)generating `popular.popular`, see:
        data.py  popular.generate_popular_list()

        Ideally, solr should be used as cache instead of hard-coded as `popular.popular`.

    Returns:
        returns a tuple (available_books, waitlisted_books)

    """
    available_books = []
    waitlisted_books = []
    seeds = popular.popular

    while seeds and len(available_books) < available_limit:
        batch = seeds[:loan_check_batch_size]
        seeds = seeds[loan_check_batch_size:]
        random.shuffle(batch)

        responses = lending.is_borrowable([seed[0] for seed in batch])

        for seed in batch:
            ocaid, key = seed
            if len(available_books) == available_limit:
                continue

            book_data = web.ctx.site.get(key)
            if book_data:
                book = format_book_data(book_data)

                if ocaid not in responses:
                    # If book is not accounted for, err on the side of inclusion
                    available_books.append(book)
                elif 'status' in responses[ocaid]:
                    if responses[ocaid]['status'] == 'available':
                        available_books.append(book)
                    elif len(waitlisted_books) < waitlist_limit:
                        waitlisted_books.append(book)
    return storify(available_books), storify(waitlisted_books)

@public
def carousel_from_list(key, randomize=False, limit=60):
    css_id = key.split("/")[-1] + "_carousel"

    data = format_list_editions(key)
    if randomize:
        random.shuffle(data)
    data = data[:limit]
    add_checkedout_status(data)
    return render_template(
        "books/carousel", storify(data), id=css_id, pixel="CarouselList")

def add_checkedout_status(books):
    """OBSOLETE -- will be deleted.
    """
    # This is not very efficient approach.
    # Todo: Implement the following apprach later.
    # * Store the borrow status of all books in the list in memcache
    # * Use that info to add checked_out status
    # * Invalidate that on any borrow/return
    for book in books:
        if book.get("borrow_url"):
            doc = web.ctx.site.store.get("ebooks" + book['key']) or {}
            checked_out = doc.get("borrowed") == "true"
        else:
            checked_out = False
        book['checked_out'] = checked_out

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
        'books/carousel', storify(books), id=cssid, pixel=pixel
    ) if books else ''


@public
def render_returncart(limit=60, randomize=True):
    data = get_returncart(limit*5)

    # Remove all inlibrary books if we not in a participating library
    if not inlibrary.get_library():
        data = [d for d in data if 'inlibrary_borrow_url' not in d]

    if randomize:
        random.shuffle(data)
    data = data[:limit]
    return render_template("books/carousel", storify(data), id="returncart_carousel", pixel="CarouselReturns")

def get_returncart(limit):
    if 'env' not in web.ctx:
        delegate.fakeload()

    items = web.ctx.site.store.items(type='ebook', name='borrowed', value='false', limit=limit)
    identifiers = [doc['identifier'] for k, doc in items if 'identifier' in doc]
    keys = web.ctx.site.things({"type": "/type/edition", "ocaid": identifiers})
    books = web.ctx.site.get_many(keys)
    return [format_book_data(book) for book in books if book.type.key == '/type/edition']

# cache the results of get_returncart in memcache for 60 sec
get_returncart = cache.memcache_memoize(get_returncart, "home.get_returncart", timeout=60)

@public
def readonline_carousel(cssid='classics_carousel', pixel="CarouselClassics"):
    """Return template code for books pulled from search engine.
       TODO: If problems, use stock list.
    """
    try:
        data = random_ebooks()
        if len(data) > 120:
            data = random.sample(data, 120)
        return render_template(
            "books/carousel", storify(data), id=cssid, pixel=pixel)
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
    d.key = book.key
    d.url = book.url()
    d.title = book.title or None

    def get_authors(doc):
        return [web.storage(key=a.key, name=a.name or None) for a in doc.get_authors()]

    if 'work_id' in book:
        d.work_id = book['work_id']

    work = book.works and book.works[0]
    if work:
        d.authors = get_authors(work)
    else:
        d.authors = get_authors(book)

    cover = book.get_cover()
    if cover:
        d.cover_url = cover.url("M")

    ia_id = book.get("ocaid")
    if ia_id:
        d.ocaid = ia_id
        collections = ia.get_meta_xml(ia_id).get("collection", [])
        if 'printdisabled' in collections or 'lendinglibrary' in collections:
            d.daisy_url = book.url("/daisy")

        if 'lendinglibrary' in collections:
            d.borrow_url = book.url("/borrow")
        elif 'inlibrary' in collections:
            d.inlibrary_borrow_url = book.url("/borrow")
        else:
            d.read_url = book.url("/borrow")
    return d

def setup():
    pass
