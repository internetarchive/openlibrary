"""Language pages
"""
from infogami.utils import delegate, stats
from infogami.utils.view import render_template, safeint
import web
import simplejson
import logging
import urllib

from . import subjects
from . import search

logger = logging.getLogger("openlibrary.worksearch")


def get_language_name(code):
    doc = web.ctx.site.get('/languages/' + code)
    name = doc and doc.name
    return name or code

class languages(subjects.subjects):
    path = '(/languages/[^_][^/]*)'

    def GET(self, key):
        page = subjects.get_subject(key, details=True)
        page.name = get_language_name(key.split("/")[-1])

        if page.work_count == 0:
 	    web.ctx.status = "404 Not Found"
            return render_template('languages/notfound.tmpl', key)

        return render_template("languages/view", page)

    def is_enabled(self):
        return "languages" in web.ctx.features

class languages_json(subjects.subjects_json):
    path = '(/languages/[^_][^/]*)'
    encoding = "json"

    def is_enabled(self):
        return "languages" in web.ctx.features
        
    def normalize_key(self, key):
        return key

    def process_key(self, key):
        return key.replace("_", " ")

class language_works_json(subjects.subject_works_json):
    path = '(/languages/[^/]+)/works'
    encoding = "json"

    def is_enabled(self):
        return "languages" in web.ctx.features

    def normalize_key(self, key):
        return key

    def process_key(self, key):
        return key.replace("_", " ")

class index(delegate.page):
    path = "/languages"
    
    def GET(self):
        from . import search
        result = search.get_works_solr().select('*:*', rows=0, facets=['language'], facet_limit=500)
        languages = [web.storage(name=get_language_name(row.value), key='/languages/' + row.value, count=row.count) 
                    for row in result['facets']['language']]
        print >> web.debug, languages[:10]
        return render_template("languages/index", languages)
        
    def is_enabled(self):
        return "languages" in web.ctx.features

class language_search(delegate.page):
    path = '/search/languages'
    
    def GET(self):
        i = web.input(q="")
        solr = search.get_works_solr()
        q = {"language": i.q}
        
        result = solr.select(q, facets=["language"], fields=["language"], rows=0)
        result = self.process_result(result)
        return render_template('search/languages', i.q, result)
        
    def process_result(self, result):
        solr = search.get_works_solr()
        
        def process(p):
            return web.storage(
                name=p.value,
                key="/languages/" + p.value.replace(" ", "_"),
                count=solr.select({"language": p.value}, rows=0)['num_found']
            )
        language_facets = result['facets']['language'][:25]
        return [process(p) for p in language_facets]
        
class LanguageEngine(subjects.SubjectEngine):
    def normalize_key(self, key):
        return key
    
    def get_ebook_count(self, name, value, publish_year):
        # Query solr for this publish_year and publish_year combination and read the has_fulltext=true facet
        solr = search.get_works_solr()
        q = {
            "language": value
        }
        
        if isinstance(publish_year, list):
            q['publish_year'] = tuple(publish_year) # range
        elif publish_year:
            q['publish_year'] = publish_year
            
        result = solr.select(q, facets=["has_fulltext"], rows=0)        
        counts = dict((v.value, v.count) for v in result["facets"]["has_fulltext"])
        return counts.get('true')

def setup():
    d = web.storage(name="language", key="languages", prefix="/languages/", facet="language", facet_key="language", engine=LanguageEngine)
    subjects.SUBJECTS.append(d)
