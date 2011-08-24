"""Publisher pages
"""
from infogami.utils import delegate
from infogami.utils.view import render_template
import web

from . import subjects

class publishers(subjects.subjects):
    path = '(/publishers/[^/]+)'

    def GET(self, key):
        key = key.replace("_", " ")
        page = subjects.get_subject(key, details=True)

        if page.work_count == 0:
            return render_template('publishers/notfound.tmpl', key)

        return render_template("subjects", page)

    def is_enabled(self):
        return "publishers" in web.ctx.features

class publishers_json(subjects.subjects_json):
    path = '(/publishers/[^/]+)'
    encoding = "json"

    def is_enabled(self):
        return "publishers" in web.ctx.features

class publisher_works_json(subjects.subject_works_json):
    path = '(/publishers/[^/]+)/works'
    encoding = "json"

    def is_enabled(self):
        return "publishers" in web.ctx.features
        
class index(delegate.page):
    path = "/publishers"
    
    def GET(self):
        return render_template("publishers/index")
        
    def is_enabled(self):
        return "publishers" in web.ctx.features
        
class PublisherEngine(subjects.SubjectEngine):
    def get_ebook_count(self, name, value, publish_year):
        return 0
        
    def normalize_key(self, key):
        return key

def setup():
    d = web.storage(name="publisher", key="publishers", prefix="/publishers/", facet="publisher_facet", facet_key="publisher_facet", engine=PublisherEngine)
    subjects.SUBJECTS.append(d)