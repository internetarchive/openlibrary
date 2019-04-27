"""Controller for home page.
"""

import web
import logging
import six

from infogami.utils import delegate
from infogami.utils.view import render_template

from openlibrary.core import admin
from openlibrary.core import cache

from openlibrary.utils import dateutil
from openlibrary.plugins.upstream.utils import get_blog_feeds

logger = logging.getLogger("openlibrary.home")

class home(delegate.page):
    path = "/"

    def GET(self):
        def get_homepage():
            """Cacheable version of the homepage"""
            if 'env' not in web.ctx:
                delegate.fakeload()
            try:
                stats = admin.get_stats()
            except Exception:
                logger.error("Error in getting stats", exc_info=True)
                stats = None
            page = render_template(
                "home/index", stats=stats,
                blog_posts=get_blog_feeds()
            )
            page.v2 = True    
            return dict(page)

        # when homepage is cached, home/index.html template doesn't
        # run ctx.setdefault to set the bodyid so we must do so here:
        delegate.context.setdefault('bodyid', 'home')
        return web.template.TemplateResult(
            get_homepage() or  # XXX delete this line! Testing
            cache.memcache_memoize(
            get_homepage, "home.homepage", timeout=5 * dateutil.MINUTE_SECS)())

def setup():
    pass
