import datetime
import web
import sys

from infogami.utils.view import render_template
from infogami.utils import template, context
from openlibrary.i18n import gettext
from openlibrary.core.admin import Stats
from BeautifulSoup import BeautifulSoup

from openlibrary.plugins.openlibrary import home

def pytest_funcarg__olconfig(request):
    from infogami import config
    import copy
    
    def safecopy(data):
        if isinstance(data, list):
            return [safecopy(d) for d in data]
        elif isinstance(data, web.storage):
            return web.storage((k, safecopy(v)) for k, v in data.items())
        elif isinstance(data, dict):
            return dict((k, safecopy(v)) for k, v in data.items())
        else:
            return data
    
    old_config = safecopy(config.__dict__)
    
    def undo():
        config.__dict__.clear()
        config.__dict__.update(old_config)
    
    request.addfinalizer(undo)
    return config.__dict__

class MockDoc(dict):
    def __init__(self, _id, *largs, **kargs):
        self.id = _id
        super(MockDoc,self).__init__(*largs, **kargs)

    def __repr__(self):
        o = super(MockDoc, self).__repr__()
        return "<%s - %s>"%(self.id, o)
        

class TestHomeTemplates:
    def test_about_template(self, render_template):
        html = unicode(render_template("home/about"))
        assert "About the Project" in html
    
        blog = BeautifulSoup(html).find("ul", {"id": "olBlog"})
        assert blog is not None
        assert len(blog.findAll("li")) == 0
        
        posts = [web.storage({
            "title": "Blog-post-0",
            "link": "http://blog.openlibrary.org/2011/01/01/blog-post-0",
            "pubdate": datetime.datetime(2011, 01, 01)
        })]
        html = unicode(render_template("home/about", blog_posts=posts))
        assert "About the Project" in html
        assert "Blog-post-0" in html
        assert "http://blog.openlibrary.org/2011/01/01/blog-post-0" in html

        blog = BeautifulSoup(html).find("ul", {"id": "olBlog"})
        assert blog is not None
        assert len(blog.findAll("li")) == 1
        
    def test_stats_template(self, render_template):
        # Make sure that it works fine without any input (skipping section)
        html = unicode(render_template("home/stats"))
        assert html == ""
        
    def test_read_template(self, render_template):
        # getting read-online books fails because solr is not defined.
        # Empty list should be returned when there is error.
        html = unicode(render_template("home/read"))
        assert html.strip() == ""
        
    def test_lending_template(self, render_template, mock_site, olconfig):
        html = unicode(render_template("home/lendinglibrary"))
        assert html.strip() == ""
        
        mock_site.quicksave("/people/foo/lists/OL1L", "/type/list")
        olconfig.setdefault("home", {})['lending_list'] = "/people/foo/lists/OL1L"

        html = unicode(render_template("home/lendinglibrary", "/people/foo/lists/OL1L"))
        assert "Lending Library" in html

    def test_returncart_template(self, render_template, mock_site, olconfig):
        html = unicode(render_template("home/returncart"))
        assert html.strip() == ""

        mock_site.quicksave("/people/foo/lists/OL1L", "/type/list")
        olconfig.setdefault("home", {})['returncart_list'] = "/people/foo/lists/OL1L"

        html = unicode(render_template("home/returncart", "/people/foo/lists/OL1L"))
        assert "Return Cart" in html

    def test_home_template(self, render_template, mock_site, olconfig):
        docs = [MockDoc(_id = datetime.datetime.now().strftime("counts-%Y-%m-%d"),
                        human_edits = 1, bot_edits = 1, lists = 1,
                        visitors = 1, loans = 1, members = 1,
                        works = 1, editions = 1, ebooks = 1,
                        covers = 1, authors = 1, subjects = 1)]* 100
        stats = dict(human_edits = Stats(docs, "human_edits", "human_edits"),
                     bot_edits   = Stats(docs, "bot_edits", "bot_edits"),
                     lists       = Stats(docs, "lists", "total_lists"),
                     visitors    = Stats(docs, "visitors", "visitors"),
                     loans       = Stats(docs, "loans", "loans"),
                     members     = Stats(docs, "members", "total_members"),
                     works       = Stats(docs, "works", "total_works"),
                     editions    = Stats(docs, "editions", "total_editions"),
                     ebooks      = Stats(docs, "ebooks", "total_ebooks"),
                     covers      = Stats(docs, "covers", "total_covers"),
                     authors     = Stats(docs, "authors", "total_authors"),
                     subjects    = Stats(docs, "subjects", "total_subjects"))
                     
        mock_site.quicksave("/people/foo/lists/OL1L", "/type/list")
        olconfig.setdefault("home", {})['returncart_list'] = "/people/foo/lists/OL1L"
        olconfig.setdefault("home", {})['lending_list'] = "/people/foo/lists/OL1L"
                     
        html = unicode(render_template("home/index", 
            stats=stats, 
            returncart_list="/people/foo/lists/OL1L",
            lending_list="/people/foo/lists/OL1L"))
        assert '<div class="homeSplash"' in html
        #assert "Books to Read" in html
        assert "Return Cart" in html
        assert "Around the Library" in html
        assert "About the Project" in html

class TestCarouselItem:
    def setup_method(self, m):
        context.context.features = []
        
    def render(self, book):
        # Anand: sorry for the hack.
        print sys._getframe(1)
        render_template = sys._getframe(1).f_locals['render_template']
        
        if "authors" in book:
            book["authors"] = [web.storage(a) for a in book['authors']]
        
        return unicode(render_template("books/carousel_item", web.storage(book)))
        
    def link_count(self, html):
        links = BeautifulSoup(html).findAll("a") or []
        return len(links)
    
    def test_with_cover_url(self, render_template):
        book = {
            "url": "/books/OL1M",
            "title": "The Great Book",
            "authors": [{"key": "/authors/OL1A", "name": "Some Author"}],
            "cover_url": "http://covers.openlibrary.org/b/id/1-M.jpg"
        }
        assert book['title'] in self.render(book)
        assert book['cover_url'] in self.render(book)
        assert self.link_count(self.render(book)) == 1

    def test_without_cover_url(self, render_template):
        book = {
            "url": "/books/OL1M",
            "title": "The Great Book",
            "authors": [{"key": "/authors/OL1A", "name": "Some Author"}],
        }
        assert book['title'] in self.render(book)
        assert self.link_count(self.render(book)) == 1
        
        del book['authors']
        assert book['title'] in self.render(book)
        assert self.link_count(self.render(book)) == 1
        
    def test_urls(self, render_template):
        book = {
            "url": "/books/OL1M",
            "title": "The Great Book",
            "authors": [{"key": "/authors/OL1A", "name": "Some Author"}],
            "cover_url": "http://covers.openlibrary.org/b/id/1-M.jpg",
            "read_url": "http://www.archive.org/stream/foo",
            "borrow_url": "/books/OL1M/foo/borrow",
            "daisy_url": "/books/OL1M/foo/daisy",
            "overdrive_url": "http://overdrive.com/foo",
        }
        
        # Remove urls on order and make sure the template obeys the expected priority
        assert 'Read online' in self.render(book)
        assert book['read_url'] in self.render(book)
        assert self.link_count(self.render(book)) == 2        
        
        del book['read_url']
        assert 'Borrow this book' in self.render(book)
        assert book['borrow_url'] in self.render(book)
        assert self.link_count(self.render(book)) == 2

        del book['borrow_url']
        assert 'DAISY' in self.render(book)
        assert book['daisy_url'] in self.render(book)
        assert self.link_count(self.render(book)) == 2

        del book['daisy_url']
        assert 'Borrow this book' in self.render(book)
        assert book['overdrive_url'] in self.render(book)
        assert self.link_count(self.render(book)) == 2

        del book['overdrive_url']
        assert self.link_count(self.render(book)) == 1
        
    def test_inlibrary(self, monkeypatch, render_template):
        book = {
            "url": "/books/OL1M",
            "title": "The Great Book",
            "authors": [{"key": "/authors/OL1A", "name": "Some Author"}],
            "cover_url": "http://covers.openlibrary.org/b/id/1-M.jpg",
            "inlibrary_borrow_url": "/books/OL1M/foo/borrow-inlibrary",
        }
        
        assert book['inlibrary_borrow_url'] not in self.render(book)
        assert self.link_count(self.render(book)) == 1
        
        g = web.template.Template.globals
        monkeypatch.setattr(web.template.Template, "globals", dict(g, get_library=lambda: {"name": "IA"}))
        monkeypatch.setattr(context.context, "features", ["inlibrary"], raising=False)

        assert book['inlibrary_borrow_url'] in self.render(book)
        assert self.link_count(self.render(book)) == 2
        
class Test_carousel:
    def test_carousel(self, render_template):
        book = web.storage({
            "url": "/books/OL1M",
            "title": "The Great Book",
            "authors": [web.storage({"key": "/authors/OL1A", "name": "Some Author"})],
            "cover_url": "http://covers.openlibrary.org/b/id/1-M.jpg"
        })
        html = unicode(render_template("books/carousel", [book]))
        
        assert book['title'] in html
        assert book['cover_url'] in html
        
        soup = BeautifulSoup(html)
        assert len(soup.findAll("li")) == 1
        assert len(soup.findAll("a")) == 1

class Test_format_book_data:        
    def test_all(self, mock_site, mock_ia):
        book = mock_site.quicksave("/books/OL1M", "/type/edition", title="Foo")
        work = mock_site.quicksave("/works/OL1W", "/type/work", title="Foo")
                
    def test_cover_url(self, mock_site, mock_ia):
        book = mock_site.quicksave("/books/OL1M", "/type/edition", title="Foo")
        assert home.format_book_data(book).get("cover_url") is None
        
        book = mock_site.quicksave("/books/OL1M", "/type/edition", title="Foo", covers=[1, 2])
        assert home.format_book_data(book).get("cover_url") == "http://covers.openlibrary.org/b/id/1-M.jpg"
        
    def test_authors(self, mock_site, mock_ia):
        a1 = mock_site.quicksave("/authors/OL1A", "/type/author", name="A1")
        a2 = mock_site.quicksave("/authors/OL2A", "/type/author", name="A2")
        work = mock_site.quicksave("/works/OL1W", "/type/work", title="Foo", authors=[{"author": {"key": "/authors/OL2A"}}])
        
        book = mock_site.quicksave("/books/OL1M", "/type/edition", title="Foo")
        assert home.format_book_data(book)['authors'] == []
        
        # when there is no work and authors, the authors field must be picked from the book
        book = mock_site.quicksave("/books/OL1M", "/type/edition", title="Foo", authors=[{"key": "/authors/OL1A"}])
        assert home.format_book_data(book)['authors'] == [{"key": "/authors/OL1A", "name": "A1"}]
        
        # when there is work, the authors field must be picked from the work
        book = mock_site.quicksave("/books/OL1M", "/type/edition", 
            title="Foo", 
            authors=[{"key": "/authors/OL1A"}], 
            works=[{"key": "/works/OL1W"}]
        )
        assert home.format_book_data(book)['authors'] == [{"key": "/authors/OL2A", "name": "A2"}]