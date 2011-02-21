import datetime
import web
from infogami.utils.view import render_template
from infogami.utils import template
from openlibrary.i18n import gettext
from openlibrary.core.admin import Stats
from BeautifulSoup import BeautifulSoup

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
        html = unicode(render_template("home/read"))
        assert "Books to Read" in html
        
    def test_borrow_template(self, render_template):
        html = unicode(render_template("home/borrow"))
        assert "Return Cart" in html

    def test_home_template(self, render_template):
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
        html = unicode(render_template("home/index", stats))
        assert '<div class="homeSplash"' in html
        assert "Books to Read" in html
        assert "Return Cart" in html
        assert "Around the Library" in html
        assert "About the Project" in html
