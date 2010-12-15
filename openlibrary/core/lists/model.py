"""Helper functions used by the List model.
"""
from collections import defaultdict
import re
import urllib, urllib2

import couchdb
import simplejson
import web

from infogami import config
from infogami.infobase import client, common
from infogami.utils import stats

from openlibrary.core import helpers as h

def cached_property(name, getter):
    """Just like property, but the getter is called only for the first access. 

    All subsequent accesses will use the cached value.
    
    The name argument must be same as the property name.
    
    Sample Usage:
    
        count = cached_property("count", get_count)
    """
    def f(self):
        value = getter(self)
        self.__dict__[name] = value
        return value

    return property(f)    

class ListMixin:
    def _get_rawseeds(self):
        def process(seed):
            if isinstance(seed, basestring):
                return seed
            else:
                return seed['key']
                
        return [process(seed) for seed in self.seeds]
        
    def _get_seed_summary(self):
        rawseeds = self._get_rawseeds()
        
        db = self._get_seeds_db()
    
        zeros = {"editions": 0, "works": 0, "ebooks": 0, "last_update": ""}
        d = dict((seed, web.storage(zeros)) for seed in rawseeds)
    
        for row in self._couchdb_view(db, "_all_docs", keys=rawseeds, include_docs=True):
            if 'doc' in row:
                if 'edition' not in row.doc:
                    doc = web.storage(zeros, **row.doc)
                    
                    # if seed info is not yet created, display edition count as 1
                    if doc.editions == 0 and row.key.startswith("/books"):
                        doc.editions = 1
                    d[row.key] = doc
        return d
        
    def _couchdb_view(self, db, viewname, **kw):
        stats.begin("couchdb", db=db.name, view=viewname, kw=kw)
        try:
            result = db.view(viewname, **kw)
        finally:
            stats.end()
        return result
        
    def _get_edition_count(self):
        return sum(seed['editions'] for seed in self.seed_summary.values())

    def _get_work_count(self):
        return sum(seed['works'] for seed in self.seed_summary.values())

    def _get_ebook_count(self):
        return sum(seed['ebooks'] for seed in self.seed_summary.values())
        
    def _get_last_update(self):
        dates = [seed.last_update for seed in self.get_seeds() if seed.last_update]
        d = dates and max(dates) or None
        return d

    seed_summary = cached_property("seed_summary", _get_seed_summary)
    
    work_count = cached_property("work_count", _get_work_count)
    edition_count = cached_property("edition_count", _get_edition_count)
    ebook_count = cached_property("ebook_count", _get_ebook_count)
    last_update = cached_property("last_update", _get_last_update)
        
    def get_works(self, limit=50, offset=0):
        keys = [[seed, "works"] for seed in self._get_rawseeds()]
        rows = self._seeds_view(keys=keys, reduce=False, limit=limit, skip=offset)
        return web.storage({
            "count": self.work_count,
            "works": [row.value for row in rows]
        })
        
    def get_couchdb_docs(self, db, keys):
        return dict((row.id, row.doc) for row in db.view("_all_docs", keys=keys, include_docs=True))

    def get_editions(self, limit=50, offset=0, _raw=False):
        """Returns the editions objects belonged to this list ordered by last_modified. 
        
        When _raw=True, the edtion dicts are returned instead of edtion objects.
        """
        d = self._editions_view(self._get_rawseeds(), 
            skip=offset, limit=limit, 
            sort="last_modified", reverse="true", 
            stale="ok")
        
        # couchdb-lucene is single-threaded. Get docs from couchdb instead of
        # passing include_docs=True to couchdb-lucene to reduce load on it.
        docs = self.get_couchdb_docs(self._get_editions_db(), [row['id'] for row in d['rows']])

        def get_doc(row):
            doc = docs[row['id']]
            del doc['_id']
            del doc['_rev']
            if not _raw:
                data = self._site._process_dict(common.parse_query(doc))
                doc = client.create_thing(self._site, doc['key'], data)
            return doc
        
        return {
            "count": d['total_rows'],
            "offset": d.get('skip', 0),
            "limit": d['limit'],
            "editions": [get_doc(row) for row in d['rows']]
        }
        
    def _preload(self, keys):
        keys = list(set(keys))
        return self._site.get_many(keys)
        
    def preload_works(self, editions):
        return self._preload(w.key for e in editions 
                                   for w in e.get('works', []))
        
    def preload_authors(self, editions):
        works = self.preload_works(editions)
        return self._preload(a.author.key for w in works
                                          for a in w.get("authors", [])
                                          if "author" in a)
                            
    def load_changesets(self, editions):
        """Adds "recent_changeset" to each edition.
        
        The recent_changeset will be of the form:
            {
                "id": "...",
                "author": {
                    "key": "..", 
                    "displayname", "..."
                }, 
                "timestamp": "...",
                "ip": "...",
                "comment": "..."
            }
         """
        for e in editions:
            if "recent_changeset" not in e:
                try:
                    e['recent_changeset'] = self._site.recentchanges({"key": e.key, "limit": 1})[0]
                except IndexError:
                    pass
    
    def _get_all_subjects(self):
        d = defaultdict(list)
        
        for seed in self.seed_summary.values():
            for s in seed.get("subjects", []):
                d[s['key']].append(s)
                
        def subject_url(s):
            if s.startswith("subject:"):
                return "/subjects/" + s.split(":", 1)[1]
            else:
                return "/subjects/" + s                
                
        subjects = [
            web.storage(
                key=key, 
                url=subject_url(key),
                count=sum(s['count'] for s in values), 
                name=values[0]["name"],
                title=values[0]["name"]
                )
            for key, values in d.items()]

        return sorted(subjects, reverse=True, key=lambda s: s["count"])
        
    def get_top_subjects(self, limit=20):
        return self._get_all_subjects()[:limit]
        
    def get_subjects(self, limit=20):
        def get_subject_type(s):
            if s.url.startswith("/subjects/place:"):
                return "places"
            elif s.url.startswith("/subjects/person:"):
                return "people"
            elif s.url.startswith("/subjects/time:"):
                return "times"
            else:
                return "subjects"
        
        d = web.storage(subjects=[], places=[], people=[], times=[])

        for s in self._get_all_subjects():
            kind = get_subject_type(s)
            if len(d[kind]) < limit:
                d[kind].append(s)
        return d
        
    def get_seeds(self):
        seeds = [Seed(self, s) for s in self.seeds]
        seeds.sort(key=lambda seed: seed.last_update, reverse=True)
        return seeds
        
    def get_seed(self, seed):
        if isinstance(seed, dict):
            seed = seed['key']
        return Seed(self, seed)
        
    def has_seed(self, seed):
        if isinstance(seed, dict):
            seed = seed['key']
        return seed in self._get_rawseeds()
        
    def get_default_cover(self):
        for s in self.get_seeds():
            cover = s.get_cover()
            if cover:
                return cover
    
    def _get_seeds_db(self):
        db_url = config.get("lists", {}).get("seeds_db")
        if not db_url:
            return None
        
        return couchdb.Database(db_url)
        
    def _get_editions_db(self):
        db_url = config.get("lists", {}).get("editions_db")
        if not db_url:
            return None
        
        return couchdb.Database(db_url)
        
    def _updates_view(self, **kw):
        view_url = config.get("lists", {}).get("updates_view")
        if not view_url:
            return []
            
        kw['stale'] = 'ok'
        view = couchdb.client.PermanentView(view_url, "updates_view")
        return view(**kw)

    def _editions_view(self, seeds, **kw):
        reverse = str(kw.pop("reverse", "")).lower()
        if 'sort' in kw and reverse == "true":
            # sort=\field is the couchdb-lucene's way of telling ORDER BY field DESC
            kw['sort'] = '\\' + kw['sort']
        view_url = config.get("lists", {}).get("editions_view")
        if not view_url:
            return {}

        def escape(value):
            special_chars = '+-&|!(){}[]^"~*?:\\'
            pattern = "([%s])" % re.escape(special_chars)
            
            quote = '"'
            return quote + web.re_compile(pattern).sub(r'\\\1', value) + quote
        
        q = " OR ".join("seed:" + escape(seed.encode('utf-8')) for seed in seeds)
        url = view_url + "?" + urllib.urlencode(dict(kw, q=q))
        
        stats.begin("couchdb", url=url)
        try:
            json = urllib2.urlopen(url).read()
        finally:
            stats.end()
        return simplejson.loads(json)

def valuesort(d):
    """Sorts the keys in the dictionary based on the values.
    """
    return sorted(d, key=lambda k: d[k])
    
class Seed:
    """Seed of a list.
    
    Attributes:
        * work_count
        * edition_count
        * ebook_count
        * last_update
        * type - "edition", "work" or "subject"
        * document - reference to the edition/work document
        * title
        * url
        * cover
    """
    def __init__(self, list, value):
        self._list = list
        
        if isinstance(value, basestring):
            self.document = None
            self.key = value
            self.type = "subject"
        else:
            self.document = value
            self.key = value.key
            
            type = self.document.type.key
            
            if type == "/type/edition":
                self.type = "edition"
            elif type == "/type/work":
                self.type = "work"
            elif type == "/type/author":
                self.type = "author"
            else:
                self.type = "unknown"
    
    def _get_summary(self):
        summary = self._list.seed_summary
        return summary.get(self.key, defaultdict(lambda: 0))
        
    def get_title(self):
        if self.type == "work" or self.type == "edition":
            return self.document.title or self.key
        elif self.type == "author":
            return self.document.name or self.key
        elif self.type == "subject":
            return self._get_subject_title()
        else:
            return self.key
    
    def _get_subject_title(self):
        subjects = self._get_summary().get("subjects")
        if subjects:
            return subjects[0]['name']
        else:
            return self.key.replace("_", " ")
            
    def get_url(self):
        if self.document:
            return self.document.url()
        else:
            if self.key.startswith("subject:"):
                return "/subjects/" + web.lstrips(self.key, "subject:")
            else:
                return "/subjects/" + self.key
            
    def get_cover(self):
        if self.type in ['work', 'edition']:
            return self.document.get_cover()
        elif self.type == 'author':
            return self.document.get_photo()
        else:
            return None
            
    def _get_last_update(self):
        date = self._get_summary().get("last_update") or None
        return date and h.parse_datetime(date)
        
    work_count = property(lambda self: self._get_summary()['works'])
    edition_count = property(lambda self: self._get_summary()['editions'])
    ebook_count = property(lambda self: self._get_summary()['ebooks'])
    last_update = property(_get_last_update)
    
    title = property(get_title)
    url = property(get_url)
    cover = property(get_cover)
    
    def __repr__(self):
        return "<seed: %s %s>" % (self.type, self.key)
    __str__ = __repr__
    
def crossproduct(A, B):
    return [(a, b) for a in A for b in B]