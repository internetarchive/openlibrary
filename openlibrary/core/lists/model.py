"""Helper functions used by the List model.
"""
from collections import defaultdict

from infogami import config
import couchdb


def cached_property(name, getter):
    """Just like property, but the getter is called only for the first access. 

    All subsequent accesses will use the cached value.
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
        
    def _get_db(self):
        db_url = config.lists['db']
        return couchdb.Database(db_url)
        
    def _get_seed_summary(self):
        db = self._get_db()

        rawseeds = self._get_rawseeds()
        keys = crossproduct(rawseeds, ['works', 'editions', 'ebooks'])
                
        d = dict((seed, {"editions": 0, "works": 0, "ebooks": 0}) for seed in rawseeds)
        
        for row in db.view("ol/lists", keys=keys, group=True):
            key, name = row.key
            d[key][name] = row.value
        
        return d

    seed_summary = cached_property("seed_summary", _get_seed_summary)
        
    def get_works(self, limit=50, offset=0):
        db = self._get_db()
        keys = [[seed, "works"] for seed in self._get_rawseeds()]
        return db.view("ol/lists", keys=keys, reduce=False, limit=limit, skip=offset)
        
    def get_seeds(self):
        return [Seed(self, s) for s in self.seeds]
    
class Seed:
    """Seed of a list.
    
    Attributes:
        * work_count
        * edition_count
        * ebook_count
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
            self.key = key
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
        
    work_count = property(lambda self: self._get_summary()['works'])
    edition_count = property(lambda self: self._get_summary()['editions'])
    ebook_count = property(lambda self: self._get_summary()['ebooks'])
    
    title = property(get_title)
    url = property(get_url)
    cover = property(get_cover)
    
def crossproduct(A, B):
    return [(a, b) for a in A for b in B]