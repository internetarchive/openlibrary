"""
Book reviews plugin.
"""
import web, infogami
from infogami.utils import delegate
from infogami.utils.template import render

import db, dev, forms, reviewsources, utils
import schema as _

@infogami.action
def install_bookrev():
    for name, properties in [_.reviewsource, _.bookreview, _.vote, _.comment]:
        db.create_type(name, properties)
    for type, prop, ref_type, ref_prop in _.backreferences:
        db.insert_backreference(type, prop, ref_type, ref_prop)

@infogami.action
def _write_a_review():
    dev.simple_shell()

@infogami.action
def _list_reviews():
    dev.list_latest_reviews()

error = web.notfound

class addreview(delegate.page):
    @utils.require_user
    def GET(self, site, user):
        i = web.input('edition')
        edition = db.get_thing(i.edition, db.get_type('type/edition'))
        if not edition:
            return error()
        form = forms.review_form()
        form.fill(edition=edition.name)
        return render.addreview(user, edition, form)

    @utils.require_user
    def POST(self, site, user):
        form = forms.review_form()
        if form.validates():
	    edition = db.get_thing(form.d.edition, db.get_type('type/edition'))
	    if not edition:
		return error()
            review = db.insert_book_review(edition, 
                                           user, 
                                           reviewsources.data.get('web'), 
                                           form.d.text,
                                           title=form.d.title)
            return web.redirect('/' + edition.name + '#reviews')
        else:
	    edition = db.get_thing(form.d.edition, db.get_type('type/edition'))
	    if not edition:
		return error()
            return render.addreview(user, edition, form)

