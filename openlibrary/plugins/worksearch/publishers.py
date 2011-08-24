"""Publisher pages
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

class publisher_search(delegate.page):
    path = '/search/publishers'
    
    def GET(self):
        i = web.input(q="")
        solr = search.get_works_solr()
        q = {"publisher": i.q}
        
        result = solr.select(q, facets=["publisher_facet"], fields=["publisher", "publisher_facet"], rows=2)
        result = self.process_result(result)
        return render_template('search/publishers', i.q, result)
        
    def process_result(self, result):
        solr = search.get_works_solr()
        
        def process(p):
            return web.storage(
                name=p.value,
                key="/publishers/" + p.value.replace(" ", "_"),
                count=solr.select({"publisher_facet": p.value}, rows=0)['num_found']
            )
        publisher_facets = result['facets']['publisher_facet'][:25]
        return [process(p) for p in publisher_facets]
        
class PublisherEngine(subjects.SubjectEngine):
    def normalize_key(self, key):
        return key
    
    def get_ebook_count(self, name, value, publish_year):
        # TODO: compute ebook_count per year.
        return 0
        
        # XXX-Anand: The following implementation is not working.
        
        #q = 'publisher_facet:(%s)' % (subjects.re_chars.sub(r'\\\1', value).encode('utf-8'))
        #years = subjects.execute_ebook_count_query(q)
        try:
            years = self._find_ebook_count(value)
        except:
            logger.error("failed to find_ebook_count", exc_info=True)
            return 0
        
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
    
    def _find_ebook_count(self, publisher_name):
        
        publisher_facet = subjects.re_chars.sub(r'\\\1', publisher_name).encode('utf-8')
        q = "publisher_facet:(%s) AND (overdrive_s:* OR ia:*)" % (publisher_facet)
        return subjects.execute_ebook_count_query()
        
        url = subjects.solr_select_url + "?" + urllib.urlencode({
            "q": q,
            "wt": "json",
            "rows": 0,
            "q.op": "AND",
            "facet": "true",
            "facet.field": "publish_year",
            "facet.limit": 10000,
            "facet.mincount": 1
        })

        stats.begin("solr", url=url)
        response = simplejson.load(urllib.urlopen(url))['response']
        stats.end()
                
        facets = response['facet_counts']['facet_fields']['publish_year']
        years = dict(web.group(facets, 2))
        return years

def setup():
    d = web.storage(name="publisher", key="publishers", prefix="/publishers/", facet="publisher_facet", facet_key="publisher_facet", engine=PublisherEngine)
    subjects.SUBJECTS.append(d)