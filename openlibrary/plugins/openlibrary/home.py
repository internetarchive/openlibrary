"""Controller for home page.
"""
import web

from infogami.utils import delegate
from infogami.utils.view import render_template

from openlibrary.core import admin
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
    
def setup():
    pass
