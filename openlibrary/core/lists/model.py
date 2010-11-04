"""Helper functions used by the List model.
"""
from collections import defaultdict
import couchdb
import web
from infogami import config

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
    
        d = dict((seed, web.storage({"editions": 0, "works": 0, "ebooks": 0, "last_update": ""})) for seed in rawseeds)
    
        print "couchdb.view", db, rawseeds
        for row in db.view("_all_docs", keys=rawseeds, include_docs=True):
            if 'doc' in row:
                d[row.key] = web.storage(row.doc)
            
        print d
        return d
        
    def _get_edition_count(self):
        return sum(seed['editions'] for seed in self.seed_summary.values())

    def _get_work_count(self):
        return sum(seed['works'] for seed in self.seed_summary.values())

    def _get_ebook_count(self):
        return sum(seed['ebooks'] for seed in self.seed_summary.values())

    seed_summary = cached_property("seed_summary", _get_seed_summary)
    
    work_count = cached_property("work_count", _get_work_count)
    edition_count = cached_property("edition_count", _get_edition_count)
    ebook_count = cached_property("ebook_count", _get_ebook_count)
        
    def get_works(self, limit=50, offset=0):
        keys = [[seed, "works"] for seed in self._get_rawseeds()]
        rows = self._seeds_view(keys=keys, reduce=False, limit=limit, skip=offset)
        return web.storage({
            "count": self.work_count,
            "works": [row.value for row in rows]
        })

    def get_editions(self, limit=50, offset=0):
        keys = [[seed, "editions"] for seed in self._get_rawseeds()]
        rows = self._seeds_view(keys=keys, reduce=False, limit=limit, skip=offset)
        return web.storage({
            "count": self.edition_count,
            "editions": [row.value for row in rows]
        })
        
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
        
    def get_subjects(self, limit=20):
        return self._get_all_subjects()[:limit]

        keys = [[seed, "subjects"] for seed in self._get_rawseeds()]
        rows = self._seeds_view(keys=keys, reduce=False)
        
        # store the counts of subject to pick the top ones
        subject_counts = defaultdict(lambda: 0)
        
        # store counts of tiles of each subject to find the most used title for each subject
        subject_titles = defaultdict(lambda: defaultdict(lambda: 0))
        
        for row in rows:
            key, title = row.value['key'], row.value['name']
            subject_counts[key] += 1
            subject_titles[key][title] += 1
            
        def subject_url(s):
            if s.startswith("subject:"):
                return "/subjects/" + s.split(":", 1)[1]
            else:
                return "/subjects/" + s
        
        def subject_title(s):
            return valuesort(subject_titles[s])[-1]
            
        subjects = [
            web.storage(title=subject_title(s), url=subject_url(s), count=count)
            for s, count in subject_counts.items()
        ]
        subjects = sorted(subjects, key=lambda s: s.count, reverse=True)
        return subjects[:limit]
        
    def get_seeds(self):
        return [Seed(self, s) for s in self.seeds]
        
    def _get_seeds_db(self):
        db_url = config.get("lists", {}).get("seeds_db")
        if not db_url:
            return {}
        
        return couchdb.Database(db_url)
        
    def _updates_view(self, **kw):
        view_url = config.get("lists", {}).get("updates_view")
        if not view_url:
            return []
            
        kw['stale'] = 'ok'
        view = couchdb.client.PermanentView(view_url, "updates_view")
        return view(**kw)

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
            return self.key.split(":")[-1]
        else:
            return self.key
            
    def get_url(self):
        if self.document:
            return self.document.url()
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
    
def crossproduct(A, B):
    return [(a, b) for a in A for b in B]