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
from openlibrary.core import cache

# this will be imported on demand to avoid circular dependency
subjects = None

def get_subject(key):
    global subjects
    if subjects is None:
        from openlibrary.plugins.worksearch import subjects
    return subjects.get_subject(key)

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
                return seed.key
                
        return [process(seed) for seed in self.seeds]
        
    def _get_seed_summary(self):
        rawseeds = self._get_rawseeds()
        
        db = self._get_seeds_db()

        zeros = {"editions": 0, "works": 0, "ebooks": 0, "last_update": ""}
        d = dict((seed, web.storage(zeros)) for seed in rawseeds)
        
        for row in self._couchdb_view(db, "_all_docs", keys=rawseeds, include_docs=True):
            if row.get('doc'):
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
            
            # force fetching the results
            result.rows
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
        if self.seed_summary:
            date = max(seed['last_update'] for seed in self.seed_summary.values()) or None
        else:
            date = None
        return date and h.parse_datetime(date)

    seed_summary = cached_property("seed_summary", _get_seed_summary)
    
    work_count = cached_property("work_count", _get_work_count)
    edition_count = cached_property("edition_count", _get_edition_count)
    ebook_count = cached_property("ebook_count", _get_ebook_count)
    last_update = cached_property("last_update", _get_last_update)
    
    def preview(self):
        """Return data to preview this list. 
        
        Used in the API.
        """
        return {
            "url": self.key,
            "full_url": self.url(),
            "name": self.name or "",
            "seed_count": len(self.seeds),
            "edition_count": self.edition_count,
            "last_update": self.last_update and self.last_update.isoformat() or None
        }
        
    def get_works(self, limit=50, offset=0):
        keys = [[seed, "works"] for seed in self._get_rawseeds()]
        rows = self._seeds_view(keys=keys, reduce=False, limit=limit, skip=offset)
        return web.storage({
            "count": self.work_count,
            "works": [row.value for row in rows]
        })
        
    def get_couchdb_docs(self, db, keys):
        try:
            stats.begin(name="_all_docs", keys=keys, include_docs=True)
            docs = dict((row.id, row.doc) for row in db.view("_all_docs", keys=keys, include_docs=True))
        finally:
            stats.end()
        return docs

    def get_editions(self, limit=50, offset=0, _raw=False):
        """Returns the editions objects belonged to this list ordered by last_modified. 
        
        When _raw=True, the edtion dicts are returned instead of edtion objects.
        """
        # show at max 10 pages
        MAX_OFFSET = min(self.edition_count, 50 * 10)
        
        if not self.seeds or offset > MAX_OFFSET:
            return {
                "count": 0,
                "offset": offset,
                "limit": limit,
                "editions": []
            }
        
        # We don't want to give more than 500 editions for performance reasons.
        if offset + limit > MAX_OFFSET:
            limit = MAX_OFFSET - offset
            
        key_data = []
        rawseeds = self._get_rawseeds()
        for seeds in web.group(rawseeds, 50):
            key_data += self._get_edition_keys(seeds, limit=MAX_OFFSET)
        keys = [key for key, last_modified in sorted(key_data, key=lambda x: x[1], reverse=True)]
        keys = keys[offset:limit]
        
        # Get the documents from couchdb 
        docs = self.get_couchdb_docs(self._get_editions_db(), keys)

        def get_doc(key):
            doc = docs[key]
            del doc['_id']
            del doc['_rev']
            if not _raw:
                data = self._site._process_dict(common.parse_query(doc))
                doc = client.create_thing(self._site, doc['key'], data)
            return doc
        
        d = {
            "count": self.edition_count,
            "offset": offset,
            "limit": limit,
            "editions": [get_doc(key) for key in keys]
        }
        
        if offset + limit < MAX_OFFSET:
            d['next_params'] = {
                'offset': offset+limit
            }
            
        if offset > 0:
            d['prev_params'] = {
                'offset': max(0, offset-limit)
            }
        return d
    
    def _get_edition_keys(self, rawseeds, offset=0, limit=500):
        """Returns a tuple of (key, last_modified) for all editions associated with given seeds.
        """
        d = self._editions_view(rawseeds,
            skip=offset, limit=limit,
            sort="last_modified", reverse="true",
            stale="ok")
        return [(row['id'], row['sort_order'][0]) for row in d['rows']]
        
    def get_all_editions(self):
        """Returns all the editions of this list in arbitrary order.
        
        The return value is an iterator over all the edtions. Each entry is a dictionary.
        (Compare the difference with get_editions.)
        
        This works even for lists with too many seeds as it doesn't try to
        return editions in the order of last-modified.
        """
        rawseeds = self._get_rawseeds()
        
        def get_edition_keys(seeds):
            d = self._editions_view(seeds, limit=10000, stale="ok")
            return [row['id'] for row in d['rows']]
            
        keys = set()
        
        # When there are too many seeds, couchdb-lucene fails because the query URL is too long.
        # Splitting the seeds into groups of 50 to avoid that trouble.
        for seeds in web.group(rawseeds, 50):
            keys.add(get_edition_keys(seeds))
        
        # Load docs from couchdb now.
        for chunk in web.group(keys, 1000):
            docs = self.get_couchdb_docs(self._get_editions_db(), chunk)
            for doc in docs:
                del doc['_id']
                del doc['_rev']
                yield doc
            
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
        
    def get_seeds(self, sort=False):
        seeds = [Seed(self, s) for s in self.seeds]
        if sort:
            seeds = h.safesort(seeds, reverse=True, key=lambda seed: seed.last_update)
        return seeds
        
    def get_seed(self, seed):
        if isinstance(seed, dict):
            seed = seed['key']
        return Seed(self, seed)
        
    def has_seed(self, seed):
        if isinstance(seed, dict):
            seed = seed['key']
        return seed in self._get_rawseeds()
    
    # cache the default_cover_id for 60 seconds
    @cache.memoize("memcache", key=lambda self: ("d" + self.key, "default-cover-id"), expires=60)
    def _get_default_cover_id(self):
        for s in self.get_seeds():
            cover = s.get_cover()
            if cover:
                return cover.id
    
    def get_default_cover(self):
        from openlibrary.core.models import Image
        cover_id = self._get_default_cover_id()
        return Image(self._site, 'b', cover_id)
        
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
        
        self.value = value
        if isinstance(value, basestring):
            self.key = value
            self.type = "subject"
        else:
            self.key = value.key
            
    def get_document(self):
        if isinstance(self.value, basestring):
            doc = get_subject(self.get_subject_url(self.value))
        else:
            doc = self.value
            
        # overwrite the property with the actual value so that subsequent accesses don't have to compute the value.
        self.document = doc
        return doc
            
    document = property(get_document)
            
    def get_type(self):
        type = self.document.type.key
        
        if type == "/type/edition":
            return "edition"
        elif type == "/type/work":
            return "work"
        elif type == "/type/author":
            return "author"
        else:
            return "unknown"
            
    type = property(get_type)
    
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
                
    def get_subject_url(self, subject):
        if subject.startswith("subject:"):
            return "/subjects/" + web.lstrips(subject, "subject:")
        else:
            return "/subjects/" + subject
            
    def get_cover(self):
        if self.type in ['work', 'edition']:
            return self.document.get_cover()
        elif self.type == 'author':
            return self.document.get_photo()
        elif self.type == 'subject':
            return self.document.get_default_cover()
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
    
    def dict(self):
        if self.type == "subject":
            url = self.url
            full_url = self.url
        else:
            url = self.key
            full_url = self.url
        
        d = {
            "url": url,
            "full_url": full_url,
            "type": self.type,
            "title": self.title,
            "work_count": self.work_count,
            "edition_count": self.edition_count,
            "ebook_count": self.ebook_count,
            "last_update": self.last_update and self.last_update.isoformat() or None
        }
        cover = self.get_cover()
        if cover:
            d['picture'] = {
                "url": cover.url("S")
            }
        return d
    
    def __repr__(self):
        return "<seed: %s %s>" % (self.type, self.key)
    __str__ = __repr__
    
def crossproduct(A, B):
    return [(a, b) for a in A for b in B]
