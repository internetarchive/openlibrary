"""Subject pages.
"""

import web
import re
import simplejson as json
import logging
from collections import defaultdict
import urllib
import datetime

from infogami import config
from infogami.plugins.api.code import jsonapi
from infogami.utils import delegate, stats
from infogami.utils.view import render_template, safeint

from openlibrary.core.models import Subject
from openlibrary.utils import str_to_key, finddict

__all__ = [
    "SubjectEngine", "get_subject"
]

# These two are available in .code module. Importing it here will result in a
# circular import. To avoid that, these values are set by the code.setup
# function.
read_author_facet = None
solr_select_url = None

logger = logging.getLogger("openlibrary.worksearch")

re_chars = re.compile("([%s])" % re.escape(r'+-!(){}[]^"~*?:\\'))
re_year = re.compile(r'\b(\d+)$')

SUBJECTS = [
    web.storage(name="person", key="people", prefix="/subjects/person:", facet="person_facet", facet_key="person_key"),
    web.storage(name="place", key="places", prefix="/subjects/place:", facet="place_facet", facet_key="place_key"),
    web.storage(name="time", key="times", prefix="/subjects/time:", facet="time_facet", facet_key="time_key"),
    web.storage(name="subject", key="subjects", prefix="/subjects/", facet="subject_facet", facet_key="subject_key"),
]

class subjects_index(delegate.page):
    path = "/subjects"
    
    def GET(self):
        return render_template("subjects/index.html")

class subjects(delegate.page):
    path = '(/subjects/[^/]+)'

    def GET(self, key):
        nkey = self.normalize_key(key)
        if nkey != key:
            raise web.redirect(nkey)
            
        page = get_subject(key, details=True)

        if page.work_count == 0:
            return render_template('subjects/notfound.tmpl', key)

        return render_template("subjects", page)
        
    def normalize_key(self, key):
        key = key.lower()

        # temporary code to handle url change from /people/ to /person:
        if key.count("/") == 3:
            key = key.replace("/people/", "/person:")
            key = key.replace("/places/", "/place:")
            key = key.replace("/times/", "/time:")
        return key

class subjects_json(delegate.page):
    path = '(/subjects/[^/]+)'
    encoding = "json"

    @jsonapi
    def GET(self, key):
        # If the key is not in the normalized form, redirect to the normalized form.
        nkey = self.normalize_key(key)
        if nkey != key:
            raise web.redirect(nkey)
            
        # Does the key requires any processing before passing using it to query solr?
        key = self.process_key(key)

        i = web.input(offset=0, limit=12, details='false', has_fulltext='false', sort='editions')

        filters = {}
        if i.get('has_fulltext') == 'true':
            filters['has_fulltext'] = 'true'

        if i.get('published_in'):
            if '-' in i.published_in:
                begin, end = i.published_in.split('-', 1)

                if safeint(begin, None) is not None and safeint(end, None) is not None:
                    filters['publish_year'] = (begin, end) # range
            else:
                y = safeint(i.published_in, None)
                if y is not None:
                    filters['publish_year'] = i.published_in

        i.limit = safeint(i.limit, 12)
        i.offset = safeint(i.offset, 0)

        subject = get_subject(key, offset=i.offset, limit=i.limit, sort=i.sort, details=i.details.lower() == 'true', **filters)
        return json.dumps(subject)
        
    def normalize_key(self, key):
        return key.lower() 
        
    def process_key(self, key):
        return key

class subject_works_json(delegate.page):
    path = '(/subjects/[^/]+)/works'
    encoding = "json"

    @jsonapi
    def GET(self, key):
        # If the key is not in the normalized form, redirect to the normalized form.
        nkey = self.normalize_key(key)
        if nkey != key:
            raise web.redirect(nkey)
            
        # Does the key requires any processing before passing using it to query solr?
        key = self.process_key(key)

        i = web.input(offset=0, limit=12, has_fulltext="false")

        filters = {}
        if i.get("has_fulltext") == "true":
            filters["has_fulltext"] = "true"

        if i.get("published_in"):
            if "-" in i.published_in:
                begin, end = i.published_in.split("-", 1)

                if safeint(begin, None) is not None and safeint(end, None) is not None:
                    filters["publish_year"] = (begin, end)
            else:
                y = safeint(i.published_in, None)
                if y is not None:
                    filters["publish_year"] = i.published_in

        i.limit = safeint(i.limit, 12)
        i.offset = safeint(i.offset, 0)

        subject = get_subject(key, offset=i.offset, limit=i.limit, details=False, **filters)
        return json.dumps(subject)

    def normalize_key(self, key):
        return key.lower() 

    def process_key(self, key):
        return key


def get_subject(key, details=False, offset=0, sort='editions', limit=12, **filters):
    """Returns data related to a subject.

    By default, it returns a storage object with key, name, work_count and works.
    The offset and limit arguments are used to get the works.

        >>> get_subject("/subjects/Love") #doctest: +SKIP
        {
            "key": "/subjects/Love", 
            "name": "Love",
            "work_count": 5129, 
            "works": [...]
        }

    When details=True, facets and ebook_count are additionally added to the result.

    >>> get_subject("/subjects/Love", details=True) #doctest: +SKIP
    {
        "key": "/subjects/Love", 
        "name": "Love",
        "work_count": 5129, 
        "works": [...],
        "ebook_count": 94, 
        "authors": [
            {
                "count": 11, 
                "name": "Plato.", 
                "key": "/authors/OL12823A"
            }, 
            ...
        ],
        "subjects": [
            {
                "count": 1168,
                "name": "Religious aspects", 
                "key": "/subjects/religious aspects"
            }, 
            ...
        ],
        "times": [...],
        "places": [...],
        "people": [...],
        "publishing_history": [[1492, 1], [1516, 1], ...],
        "publishers": [
            {
                "count": 57, 
                "name": "Sine nomine"        
            },
            ...
        ]
    }

    Optional arguments limit and offset can be passed to limit the number of works returned and starting offset.

    Optional arguments has_fulltext and published_in can be passed to filter the results.
    """
    def create_engine():
        for d in SUBJECTS:
            if key.startswith(d.prefix):
                Engine = d.get("engine") or SubjectEngine
                return Engine()
        return SubjectEngine()
        
    sort_options = {
        'editions': 'edition_count desc',
        'new': 'first_publish_year desc',
    }
    sort_order = sort_options.get(sort) or sort_options['editions']
    
    engine = create_engine()
    return engine.get_subject(key, details=details, offset=offset, sort=sort_order, limit=limit, **filters)

class SubjectEngine:
    def get_subject(self, key, details=False, offset=0, limit=12, sort='first_publish_year desc', **filters):
        meta = self.get_meta(key)

        q = self.make_query(key, filters)
        subject_type = meta.name
        name = meta.path.replace("_", " ")

        if details:
            kw = self.query_optons_for_details()
        else:
            kw = {}

        from search import work_search
        result = work_search(q, offset=offset, limit=limit, sort=sort, **kw)
        for w in result.docs:
            w.ia = w.ia and w.ia[0] or None
            if not w.get('public_scan') and w.ia and w.get('lending_edition'):
                doc = web.ctx.site.store.get("ebooks/books/" + w['lending_edition']) or {}
                w['checked_out'] = doc.get("borrowed") == "true"

            # XXX-Anand: Oct 2013
            # Somewhere something is broken, work keys are coming as OL1234W/works/
            # Quick fix it solve that issue.
            if w.key.endswith("/works/"):
                w.key = "/works/" + w.key.replace("/works/", "")
                
        subject = Subject(
            key=key,
            name=name,
            subject_type=subject_type,
            work_count = result['num_found'],
            works=result['docs']
        )

        if details:
            subject.ebook_count = dict(result.facets["has_fulltext"]).get("true", 0)
            #subject.ebook_count = self.get_ebook_count(meta.name, q[meta.facet_key], q.get('publish_year'))

            subject.subjects = result.facets["subject_facet"]
            subject.places = result.facets["place_facet"]
            subject.people = result.facets["person_facet"]
            subject.times = result.facets["time_facet"]

            subject.authors = result.facets["author_facet"]
            subject.publishers = result.facets["publisher_facet"]
            subject.languages = result.facets['language']

            # Ignore bad dates when computing publishing_history
            # year < 1000 or year > current_year+1 are considered bad dates
            current_year = datetime.datetime.utcnow().year
            subject.publishing_history = [[year, count] for year, count in result.facets["publish_year"] if 1000 < year <= current_year+1]

            # strip self from subjects and use that to find exact name
            for i, s in enumerate(subject[meta.key]):
                if "key" in s and s.key.lower() == key.lower():
                    subject.name = s.name;
                    subject[meta.key].pop(i)
                    break

        return subject

    def get_meta(self, key):
        prefix = self.parse_key(key)[0]
        meta = finddict(SUBJECTS, prefix=prefix)

        meta = web.storage(meta)
        meta.path = web.lstrips(key, meta.prefix)
        return meta

    def parse_key(self, key):
        """Returns prefix and path from the key.
        """
        for d in SUBJECTS:
            if key.startswith(d.prefix):
                return d.prefix, key[len(d.prefix):]
        return None, None

    def make_query(self, key, filters):
        meta = self.get_meta(key)
        
        q = {meta.facet_key: self.normalize_key(meta.path)}
        
        if filters:
            if filters.get("has_fulltext") == "true":
                q['has_fulltext'] = "true"
            if filters.get("publish_year"):
                q['publish_year'] = filters['publish_year']
        return q
        
    def normalize_key(self, key):
        return str_to_key(key).lower()

    def get_ebook_count(self, name, value, publish_year):
        return get_ebook_count(name, value, publish_year)
    
    def facet_wrapper(self, facet, value, count):
        if facet == "publish_year":
            return [int(value), count]
        elif facet == "publisher_facet":
            return web.storage(name=value, count=count, key="/publishers/" + value.replace(" ", "_"))
        elif facet == "author_facet":
            author = read_author_facet(value)
            return web.storage(name=author[1], key="/authors/" + author[0], count=count)
        elif facet in ["subject_facet", "person_facet", "place_facet", "time_facet"]:
            return web.storage(key=finddict(SUBJECTS, facet=facet).prefix + str_to_key(value).replace(" ", "_"), name=value, count=count)
        elif facet == "has_fulltext":
            return [value, count]
        else:
            return web.storage(name=value, count=count)
            
    def query_optons_for_details(self):
        """Additional query options to be added when details=True.
        """
        kw = {}
        kw['facets'] = [
            {"name": "author_facet", "sort": "count"},
            "language",
            "publisher_facet",
            {"name": "publish_year", "limit": -1},
            "subject_facet", "person_facet", "place_facet", "time_facet",
            "has_fulltext", "language"]
        kw['facet.mincount'] = 1
        kw['facet.limit'] = 25
        kw['facet_wrapper'] = self.facet_wrapper
        return kw


def get_ebook_count(field, key, publish_year=None):
    ebook_count_db = get_ebook_count_db()
    
    # Handle the case of ebook_count_db_parametres not specified in the config.
    if ebook_count_db is None:
        return 0
    
    def db_lookup(field, key, publish_year=None):
        sql = 'select sum(ebook_count) as num from subjects where field=$field and key=$key'
        if publish_year:
            if isinstance(publish_year, (tuple, list)):
                sql += ' and publish_year between $y1 and $y2'
                (y1, y2) = publish_year
            else:
                sql += ' and publish_year=$publish_year'
        return list(ebook_count_db.query(sql, vars=locals()))[0].num

    total = db_lookup(field, key, publish_year)
    if total:
        return total
    elif publish_year:
        sql = 'select ebook_count as num from subjects where field=$field and key=$key limit 1'
        if len(list(ebook_count_db.query(sql, vars=locals()))) != 0:
            return 0
    years = find_ebook_count(field, key)
    if not years:
        return 0
    for year, count in sorted(years.iteritems()):
        ebook_count_db.query('insert into subjects (field, key, publish_year, ebook_count) values ($field, $key, $year, $count)', vars=locals())

    return db_lookup(field, key, publish_year)

@web.memoize
def get_ebook_count_db():
    """Returns the ebook_count database. 
    
    The database object is created on the first call to this function and
    cached by memoize. Subsequent calls return the same object.
    """
    params = config.plugin_worksearch.get('ebook_count_db_parameters')
    if params:
        params.setdefault('dbn', 'postgres')
        return web.database(**params)
    else:
        logger.warn("ebook_count_db_parameters is not specified in the config. ebook-count on subject pages will be displayed as 0.")
        return None

def find_ebook_count(field, key):
    q = '%s_key:%s+AND+(overdrive_s:*+OR+ia:*)' % (field, re_chars.sub(r'\\\1', key).encode('utf-8'))
    return execute_ebook_count_query(q)
    
def execute_ebook_count_query(q):
    root_url = solr_select_url + '?wt=json&indent=on&rows=%d&start=%d&q.op=AND&q=%s&fl=edition_key'
    rows = 1000

    ebook_count = 0
    start = 0
    solr_url = root_url % (rows, start, q)
    
    stats.begin("solr", url=solr_url)
    response = json.load(urllib.urlopen(solr_url))['response']
    stats.end()

    num_found = response['numFound']
    years = defaultdict(int)
    while start < num_found:
        if start:
            solr_url = root_url % (rows, start, q)
            stats.begin("solr", url=solr_url)
            response = json.load(urllib.urlopen(solr_url))['response']
            stats.end()
        for doc in response['docs']:
            for k in doc['edition_key']:
                e = web.ctx.site.get('/books/' + k)
                ia = set(i[3:] for i in e.get('source_records', []) if i.startswith('ia:'))
                if e.get('ocaid'):
                    ia.add(e['ocaid'])
                pub_date = e.get('publish_date')
                pub_year = -1
                if pub_date:
                    m = re_year.search(pub_date)
                    if m:
                        pub_year = int(m.group(1))
                ebook_count = len(ia)
                if 'overdrive' in e.get('identifiers', {}):
                    ebook_count += len(e['identifiers']['overdrive'])
                if ebook_count:
                    years[pub_year] += ebook_count
        start += rows

    return dict(years)

def setup():
    """Placeholder for doing any setup required.
    
    This function is called from code.py.
    """
    pass