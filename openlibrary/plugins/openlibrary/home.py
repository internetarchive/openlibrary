"""Controller for home page.
"""
import random
import web
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
        loans = borrow.get_loans(user) if user else None

        return render_template(
            "home/index", stats=stats,
            blog_posts=blog_posts,
            lending_list=lending_list,
            returncart_list=returncart_list,
            user=user, loans=loans)


def get_popular_books(seeds, limit=None, loan_check_batch_size=50,
                      available_only=True):
    """Takes a list of seeds (from user lists or otherwise), checks which
    ones are (un)available (in batch sizes of
    `loan_check_batch_size`), fetches data for editions (according to
    available_only), and returns the tuple of available and
    unavailable popular works.

    Args:
        seeds (list) - seeds from a user's list

        limit (int) - Load the popular carousel with how many items?
        (preferably divisible by 6; number of books shown per page)

        loan_check_batch_size (int) - Bulk submits this many
        archive.org itemids at a time to see if they are available to
        be borrowed (only considers waitinglist and bookreader
        borrows, no acs4)

        available (bool) - return only available works? If True,
        waitlisted_books will be []

    Returns:
        returns a tuple (available_books,
        waitlisted_books). waitlisted_books will be [] if
        available_only=True

    """
    available_books = []
    waitlisted_books = []

    batch = {}
    while seeds and (limit is None or len(available_books) < limit):
        archive_ids = []
        while seeds and len(batch) < loan_check_batch_size:
            seed = seeds.pop(0)

            if not lists.seed_is_daisy_only(seed):
                edition = web.ctx.site.get(seed['key'])
                archive_id = edition.get('ocaid')
                if archive_id:
                    batch[archive_id] = edition
                    archive_ids.append(archive_id)

        responses = lending.is_borrowable(archive_ids)

        for archive_id in archive_ids:
            if len(available_books) == limit:
                continue
            if archive_id not in responses:
                # If book is not accounted for, err on the side of inclusion
                available_books.append(format_book_data(batch[archive_id]))
            else:
                status = 'status' in responses[archive_id]
                if status and responses[archive_id]['status'] == 'available':
                    available_books.append(format_book_data(batch[archive_id]))
                elif not available_only:
                    waitlisted_books.append(format_book_data(batch[archive_id]))
        batch = {}  # reset for next batch loan check

    return available_books, waitlisted_books

@public
def popular_carousel(limit=36):
    """Renders a carousel of popular editions, which are available for
    reading or borrowing, from user lists (borrowable or downloadable;
    excludes daisy only).

    Args:
        limit (int) - Load the popular carousel with how many items?
        (preferably divisible by 6; number of books shown per page)

    Selected Lists:
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

    Returns:
        A rendered html carousel with popular books.
    """
    # Pulls from one list at a time (prioritized by the perceived
    # quality of the list), shuffles its seeds, and appends to seeds
    user_lists = [
        '/people/mekBot/lists/OL104041L',
        '/people/openlibrary/lists/OL104411L'
    ]
    seeds = []
    for lst_key in user_lists:
        seeds.extend(lists.get_randomized_list_seeds(lst_key))

    available_books, _ = get_popular_books(seeds, limit=limit)

    return render_template("books/carousel", storify(available_books),
                           id='CarouselPopular')


@public
def carousel_from_list(key, randomize=False, limit=60):
    id = key.split("/")[-1] + "_carousel"

    data = format_list_editions(key)
    if randomize:
        random.shuffle(data)
    data = data[:limit]
    add_checkedout_status(data)
    return render_template("books/carousel", storify(data), id=id)

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
def loans_carousel(loans=None, css_id="CarouselLoans"):
    """Generates 'Your Loans' carousel on home page"""
    _loans = loans or []
    books = [format_book_data(web.ctx.site.get(loan['book']))
             for loan in _loans]
    return render_template(
        "books/carousel", storify(books), id=css_id
    ) if books else ""

@public
def render_returncart(limit=60, randomize=True):
    data = get_returncart(limit*5)

    # Remove all inlibrary books if we not in a participating library
    if not inlibrary.get_library():
        data = [d for d in data if 'inlibrary_borrow_url' not in d]

    if randomize:
        random.shuffle(data)
    data = data[:limit]
    return render_template("books/carousel", storify(data), id="returncart_carousel")

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
def readonline_carousel(id="read-carousel"):
    """Return template code for books pulled from search engine.
       TODO: If problems, use stock list.
    """
    try:
        data = random_ebooks()
        if len(data) > 120:
            data = random.sample(data, 120)
        return render_template("books/carousel", storify(data), id=id)
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
    """Formats the editions of the list suitable for display in carousel.
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
