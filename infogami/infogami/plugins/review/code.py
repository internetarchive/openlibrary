"""
review: allow user reviews

Creates a new set of database tables to keep track of user reviews.
Creates '/changes' page for displaying modifications since last review.
"""

from infogami.utils import delegate, view
from infogami.utils.view import render
from infogami import core
from infogami.core.auth import require_login

import db
import web

class changes (delegate.page):
    @require_login
    def GET(self, site):
        user = core.auth.get_user()
        d = db.get_modified_pages(site, user.id)
        return render.review.changes(web.ctx.homepath, d)

def input():
	i = web.input("a", "b", "c")
	i.a = (i.a and int(i.a) or 0)
	i.b = int(i.b)
	i.c = int(i.c)
	return i

class review (delegate.mode):
    @require_login
    def GET(self, site, path):
        user = core.auth.get_user()
        i = input()

        if i.a == 0:
            alines = []
            xa = web.storage(created="", revision=0)
        else:
            xa = core.db.get_version(site, path, revision=i.a)
            alines = xa.data.body.splitlines()

        xb = core.db.get_version(site, path, revision=i.b)
        blines = xb.data.body.splitlines()
        map = core.diff.better_diff(alines, blines)

        view.add_stylesheet('core', 'diff.css')
        diff = render.core.diff(map, xa, xb)
        
        return render.review.review(path, diff, i.a, i.b, i.c)
        
class approve (delegate.mode):
    @require_login
    def POST(self, site, path):
        i = input()

        if i.c != core.db.get_version(site, path).revision:
            return render.review.parallel_modification()

        user = core.auth.get_user()

        if i.b != i.c: # user requested for some reverts before approving this
            db.revert(site, path, user.id, i.b)
            revision = i.c + 1 # one new version has been added by revert
        else:
            revision = i.b

        db.approve(site, user.id, path, revision)
        web.seeother(web.changequery(m=None, a=None, b=None, c=None))

class revert (delegate.mode):
    @require_login
    def POST(self, site, path):
        i = input()

        if i.c != core.db.get_version(site, path).revision:
            return render.review.parallel_modification()
   
        if i.a == i.b:
	        return approve().POST(site, path)
        else:
            web.seeother(web.changequery(m='review', b=i.b-1))
