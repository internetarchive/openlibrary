"""Models of various OL objects.
"""

import urllib, urllib2
import simplejson
import web
from infogami.infobase import client

import helpers as h

#TODO: fix this. openlibrary.core should not import plugins.
from openlibrary.plugins.upstream.utils import get_history

# relative imports
from lists.model import ListMixin

class Image:
    def __init__(self, site, category, id):
        self._site = site
        self.category = category
        self.id = id
        
    def info(self):
        url = '%s/%s/id/%s.json' % (h.get_coverstore_url(), self.category, self.id)
        try:
            d = simplejson.loads(urllib2.urlopen(url).read())
            d['created'] = h.parse_datetime(d['created'])
            if d['author'] == 'None':
                d['author'] = None
            d['author'] = d['author'] and self._site.get(d['author'])
            
            return web.storage(d)
        except IOError:
            # coverstore is down
            return None
                
    def url(self, size="M"):
        return "%s/%s/id/%s-%s.jpg" % (h.get_coverstore_url(), self.category, self.id, size.upper())
        
    def __repr__(self):
        return "<image: %s/%d>" % (self.category, self.id)


class Thing(client.Thing):
    """Base class for all OL models."""
    def get_history_preview(self):
        if '_history_preview' not in self.__dict__:
            self.__dict__['_history_preview'] = get_history(self)
        return self._history_preview
        
    def get_most_recent_change(self):
        """Returns the most recent change.
        """
        preview = self.get_history_preview()
        if preview.recent:
            return preview.recent[0]
        else:
            return preview.initial[0]
    
    def prefetch(self):
        """Prefetch all the anticipated data."""
        preview = self.get_history_preview()
        authors = set(v.author.key for v in preview.initial + preview.recent if v.author)
        # preload them
        self._site.get_many(list(authors))
        
    def _make_url(self, label, suffix, **params):
        """Make url of the form $key/$label$suffix?$params.
        """
        u = self.key + "/" + h.urlsafe(label) + suffix
        if params:
            u += '?' + urllib.urlencode(params)
        return u
        
    def _get_lists(self):
        q = {
            "type": "/type/list",
            "seeds": {"key": self.key} 
        }
        keys = self._site.things(q)
        return self._site.get_many(keys)

class Edition(Thing):
    """Class to represent /type/edition objects in OL.
    """
    def url(self, suffix="", **params):
        return self._make_url(self.title or "untitled", suffix, **params)

    def __repr__(self):
        return "<Edition: %s>" % repr(self.title)
    __str__ = __repr__

    def full_title(self):
        # retained for backward-compatibility. Is anybody using this really?
        return self.title            

    def get_lists(self):
        return self._get_lists()

class Work(Thing):
    """Class to represent /type/work objects in OL.
    """
    def url(self, suffix="", **params):
        return self._make_url(self.title or "untitled", suffix, **params)

    def __repr__(self):
        return "<Work: %s>" % repr(self.title)
    __str__ = __repr__

    def get_edition_count(self):
        if '_editon_count' not in self.__dict__:
            self.__dict__['_editon_count'] = self._site._request(
                                                '/count_editions_by_work', 
                                                data={'key': self.key})
        return self.__dict__['_editon_count']
    
    edition_count = property(get_edition_count)

    def get_lists(self):
        return self._get_lists()

class Author(Thing):
    """Class to represent /type/author objects in OL.
    """
    def url(self, suffix="", **params):
        return self._make_url(self.name or "unnamed", suffix, **params)

    def __repr__(self):
        return "<Author: %s>" % repr(self.name)
    __str__ = __repr__

    def get_edition_count(self):
        return self._site._request(
                '/count_editions_by_author', 
                data={'key': self.key})
    edition_count = property(get_edition_count)
    
    def get_lists(self):
        return self._get_lists()
    
class User(Thing):
    def get_usergroups(self):
        keys = self._site.things({
            'type': '/type/usergroup', 
            'members': self.key})
        return self._site.get_many(keys)
    usergroups = property(get_usergroups)

    def is_admin(self):
        return '/usergroup/admin' in [g.key for g in self.usergroups]
        
    def get_lists(self, seed=None, limit=20, offset=0):
        """Returns all the lists of this user.
        
        When seed is specified, this returns all the lists which contain the
        given seed.
        
        seed could be an object or a string like "subject:cheese".
        """
        q = {
            "type": "/type/list", 
            "key~": self.key + "/lists/*",
            "limit": limit,
            "offset": offset
        }
        if seed:
            if isinstance(seed, Thing):
                seed = {"key": seed.key}
            q['seeds'] = seed
            
        keys = self._site.things(q)
        return self._site.get_many(keys)
        
    def new_list(self, name, description, seeds, tags=[]):
        """Creates a new list object with given name, description, and seeds.

        seeds must be a list containing references to author, edition, work or subject strings.

        Sample seeds:

            {"key": "/authors/OL1A"}
            {"key": "/books/OL1M"}
            {"key": "/works/OL1W"}
            "subject:love"
            "place:san_francisco"
            "time:1947"
            "person:gerge"

        The caller must call list._save(...) to save the list.
        """
        id = self._site.seq.next_value("list")

        # since the owner is part of the URL, it might be difficult to handle
        # change of ownerships. Need to think of a way to handle redirects.
        key = "%s/lists/OL%sL" % (self.key, id)
        doc = {
            "key": key,
            "type": {
                "key": "/type/list"
            },
            "name": name,
            "description": description,
            "seeds": seeds,
            "tags": tags
        }
        return self._site.new(key, doc)


class List(Thing, ListMixin):
    """Class to represent /type/list objects in OL.
    
    List contains the following properties:
    
        * name - name of the list
        * description - detailed description of the list (markdown)
        * members - members of the list. Either references or subject strings.
        * cover - id of the book cover. Picked from one of its editions.
        * tags - list of tags to describe this list.
    """
    def url(self, suffix="", **params):
        return self._make_url(self.name or "unnamed", suffix, **params)
        
    def get_owner(self):
        match = web.re_compile("(/people/\w+)/lists/OL\d+L").match(self.key)
        if match:
            key = match.group(1)
            return self._site.get(key)
    
    def _get_editions(self):
        """Returns all the editions referenced by members of this list.
        """
        #@@ Returning the editions in members instead of finding all the members.
        # This will be fixed soon.
        return [doc for doc in self.members 
            if isinstance(doc, Thing) 
            and doc.type.key == '/type/edition']
        
    def get_edition_count(self):
        """Returns the number of editions referenced by members of this list.
        """
        # Temporary implementation. will be fixed soon.
        return len(self.get_editions())
        
    def get_updates(self, offset=0, limit=20):
        """Returns the updates to the members of this list.
        """
        return []
    
    def get_update_count(self):
        """Returns the number of updates since this list is created.
        """
        return 0
        
    def get_cover(self):
        """Returns a cover object.
        """
        return self.cover and Image(self._site, "b", self.cover)
        
    def get_tags(self):
        """Returns tags as objects.
        
        Each tag object will contain name and url fields.
        """
        return [web.storage(name=t, url=self.key + u"/tags/" + t) for t in self.tags]
        
    def _get_subjects(self):
        """Returns list of subjects inferred from the seeds.
        Each item in the list will be a storage object with title and url.
        """
        # sample subjects
        return [
            web.storage(title="Cheese", url="/subjects/cheese"),
            web.storage(title="San Francisco", url="/subjects/place:san_francisco")
        ]
            
    def add_seed(self, seed):
        """Adds a new seed to this list.
        
        seed can be:
            - author, edition or work object
            - {"key": "..."} for author, edition or work objects
            - subject strings.
        """
        if isinstance(seed, Thing):
            seed = {"key": seed.key}

        index = self._index_of_seed(seed)
        if index >= 0:
            return False
        else:
            self.seeds = self.seeds or []
            self.seeds.append(seed)
            return True
        
    def remove_seed(self, seed):
        """Removes a seed for the list.
        """
        if isinstance(seed, Thing):
            seed = {"key": seed.key}
            
        index = self._index_of_seed(seed)
        if index >= 0:
            self.seeds.pop(index)
            return True
        else:
            return False
        
    def _index_of_seed(self, seed):
        for i, s in enumerate(self.seeds):
            if isinstance(s, Thing):
                s = {"key": s.key}
            if s == seed:
                return i
        return -1

class Subject(web.storage):
    def get_lists(self):
        q = {
            "type": "/type/list",
            "seeds": {"key": self.key} 
        }
        keys = self._site.things(q)
        return self._site.get_many(keys)
        
    def get_seed(self):
        seed = self.key.split("/")[-1]
        if seed.split(":")[0] not in ["place", "person", "time"]:
            seed = "subject:" + seed
        return subject

def register_models():
    client.register_thing_class(None, Thing) # default
    client.register_thing_class('/type/edition', Edition)
    client.register_thing_class('/type/work', Work)
    client.register_thing_class('/type/author', Author)
    client.register_thing_class('/type/user', User)
    client.register_thing_class('/type/list', List)
    
def register_types():
    """Register default types for various path patterns used in OL.
    """
    from infogami.utils import types

    types.register_type('^/authors/[^/]*$', '/type/author')
    types.register_type('^/books/[^/]*$', '/type/edition')
    types.register_type('^/works/[^/]*$', '/type/work')
    types.register_type('^/languages/[^/]*$', '/type/language')

    types.register_type('^/usergroup/[^/]*$', '/type/usergroup')
    types.register_type('^/permission/[^/]*$', '/type/permision')

    types.register_type('^/(css|js)/[^/]*$', '/type/rawtext')
    