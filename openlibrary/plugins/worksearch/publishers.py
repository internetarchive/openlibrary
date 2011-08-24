"""Publisher pages
"""
from infogami.utils import delegate
from infogami.utils.view import render_template, safeint
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
        
    def normalize_key(self, key):
        return key

    def process_key(self, key):
        return key.replace("_", " ")

class publisher_works_json(subjects.subject_works_json):
    path = '(/publishers/[^/]+)/works'
    encoding = "json"

    def is_enabled(self):
        return "publishers" in web.ctx.features

    def normalize_key(self, key):
        return key

    def process_key(self, key):
        return key.replace("_", " ")

        
class index(delegate.page):
    path = "/publishers"
    
    def GET(self):
        return render_template("publishers/index")
        
    def is_enabled(self):
        return "publishers" in web.ctx.features
        
class PublisherEngine(subjects.SubjectEngine):
    def get_ebook_count(self, name, value, publish_year):
        q = 'publisher_facet:(%s)' % (subjects.re_chars.sub(r'\\\1', value).encode('utf-8'))
        years = subjects.execute_ebook_count_query(q)
        
        # publish_year is None when querying for all years
        # publish_year is a string when querying for a single year
        # publish_year is a list of 2 strings, start and end years when querying for an interval
        if publish_year is None:
            return sum(years.values())
        elif isinstance(publish_year, list):
            start, end = publish_year
            start = safeint(start, 0)
            end = safeint(end, 1000)
            return sum(count for year, count in years.items() if start <= year <= end)
        else:
            y = safeint(publish_year, 0)
            return years.get(y, 0)
        return 0
        
    def normalize_key(self, key):
        return key

def setup():
    d = web.storage(name="publisher", key="publishers", prefix="/publishers/", facet="publisher_facet", facet_key="publisher_facet", engine=PublisherEngine)
    subjects.SUBJECTS.append(d)