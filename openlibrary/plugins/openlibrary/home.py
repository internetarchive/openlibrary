"""Controller for home page.
"""
import web

from infogami.utils import delegate
from infogami.utils.view import render_template

from openlibrary.core import admin, cache
from openlibrary.plugins.upstream.utils import get_blog_feeds

class home(delegate.page):
    path = "/"
    
    def is_enabled(self):
        return "lending_v2" in web.ctx.features
    
    def GET(self):
        try:
            stats = admin.get_stats()
        except Exception:
            stats = None
        blog_posts = get_blog_feeds()
        
        return render_template("home/index", 
            stats=stats,
            blog_posts=blog_posts)

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
        
    overdrive = book.get("identifiers", {}).get('overdrive')
    if overdrive:
        d.overdrive_url = "http://search.overdrive.com/SearchResults.aspx?ReserveID={%s}" % overdrive

    ia_id = book.get("ocaid")
    if ia_id:
        collections = ia.get_meta_xml(ia_id).get("collection")
        if 'printdisabled' in collections or 'lendinglibrary' in collections:
            d.daisy_url = book.url("/daisy")
        elif 'lendinglibrary' in collections:
            d.borrow_url = book.url("/borrow")
        elif 'inlibrary' in collections:
            d.inlibrary_borrow_url = book.url("/borrow")
        else:
            d.read_url = book.url("/borrow")
    return d

def setup():
    pass
