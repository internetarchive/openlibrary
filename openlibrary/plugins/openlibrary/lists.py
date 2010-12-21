"""Lists implementaion.
"""
import random

import simplejson
import web
import yaml

from infogami.utils import delegate
from infogami.utils.view import render_template, public
from infogami.infobase import client

from openlibrary.core import formats
import openlibrary.core.helpers as h

from openlibrary.plugins.worksearch import code as worksearch

class lists_home(delegate.page):
    path = "/lists"
    
    def GET(self):
        return render_template("lists/home")

class lists(delegate.page):
    """Controller for displaying lists of a seed or lists of a person.
    """
    path = "(/(?:people|books|works|authors|subjects)/[^/]+)/lists"

    def is_enabled(self):
        return "lists" in web.ctx.features
            
    def GET(self, path):
        doc = self.get_doc(path)
        if not doc:
            raise web.notfound()
            
        lists = doc.get_lists()
        return self.render(doc, lists)
        
    def get_doc(self, key):
        if key.startswith("/subjects/"):
            s = worksearch.get_subject(key)
            if s.work_count > 0:
                return s
            else:
                return None
        else:
            return web.ctx.site.get(key)
        
    def render(self, doc, lists):
        return render_template("lists/lists.html", doc, lists)
        
class lists_delete(delegate.page):
    path = "(/people/\w+/lists/OL\d+L)/delete"
    encoding = "json"

    def POST(self, key):
        doc = web.ctx.site.get(key)
        if doc is None or doc.type.key != '/type/list':
            raise web.notfound()
        
        doc = {
            "key": key,
            "type": {"key": "/type/delete"}
        }
        try:
            result = web.ctx.site.save(doc, action="lists", comment="Deleted list.")
        except client.ClientException, e:
            web.ctx.status = e.status
            web.header("Content-Type", "application/json")
            return delegate.RawText(e.json)
            
        web.header("Content-Type", "application/json")
        return delegate.RawText('{"status": "ok"}')
        
class lists_json(delegate.page):
    path = "(/(?:people|books|works|authors|subjects)/[^/]+)/lists"
    encoding = "json"
    content_type = "application/json"
    
    def GET(self, path):
        if path.startswith("/subjects/"):
            doc = worksearch.get_subject(path)
        else:
            doc = web.ctx.site.get(path)
        if not doc:
            raise web.notfound()
            
        i = web.input(offset=0, limit=50)
        i.offset = h.safeint(i.offset, 0)
        i.limit = h.safeint(i.limit, 50)
        
        i.limit = min(i.limit, 100)
        i.offset = max(i.offset, 0)
        
        lists = self.get_lists(doc, limit=i.limit, offset=i.offset)
        return delegate.RawText(self.dumps(lists))
        
    def get_lists(self, doc, limit=50, offset=0):
        lists = doc.get_lists(limit=limit, offset=offset)
        size = len(lists)
        
        if offset or len(lists) == limit:
            # There could be more lists than len(lists)
            size = len(doc.get_lists(limit=1000))
        
        d = {
            "links": {
                "self": web.ctx.path
            },
            "size": size,
            "entries": [list.preview() for list in lists]
        }
        if offset + len(lists) < size:
            d['links']['next'] = web.changequery(limit=limit, offset=offset + limit)
            
        if offset:
            offset = max(0, offset-limit)
            d['links']['prev'] = web.changequery(limit=limit, offset=offset)
            
        return d
            
    def forbidden(self):
        headers = {"Content-Type": self.get_content_type()}
        data = {
            "message": "Permission denied."
        }
        return web.HTTPError("403 Forbidden", data=self.dumps(data), headers=headers)
        
    def POST(self, user_key):
        # POST is allowed only for /people/foo/lists
        if not user_key.startswith("/people/"):
            raise web.nomethod()
        
        site = web.ctx.site
        user = site.get(user_key)
        
        if not user:
            raise web.notfound()
            
        if not site.can_write(user_key):
            raise self.forbidden()
        
        data = self.loads(web.data())
        # TODO: validate data
        
        seeds = self.process_seeds(data.get('seeds', []))
        
        list = user.new_list(
            name=data.get('name', ''),
            description=data.get('description', ''),
            tags=data.get('tags', []),
            seeds=seeds
        )
        
        try:
            result = site.save(list.dict(), 
                comment="Created new list.",
                action="lists",
                data={
                    "list": {"key": list.key},
                    "seeds": seeds
                }
            )
        except client.ClientException, e:
            headers = {"Content-Type": self.get_content_type()}
            data = {
                "message": e.message
            }
            raise web.HTTPError(e.status, 
                data=self.dumps(data),
                headers=headers)
        
        web.header("Content-Type", self.get_content_type())
        return delegate.RawText(self.dumps(result))
        
    def process_seeds(self, seeds):
        def f(seed):
            if isinstance(seed, dict):
                return seed
            elif seed.startswith("/subjects/"):
                seed = seed.split("/")[-1]
                if seed.split(":")[0] not in ["place", "person", "time"]:
                    seed = "subject:" + seed
                seed = seed.replace(",", "_").replace("__", "_")
            else:
                seed = {"key": seed}
            return seed
        return [f(seed) for seed in seeds]
                
    def get_content_type(self):
        return self.content_type
        
    def dumps(self, data):
        return formats.dump(data, self.encoding)
    
    def loads(self, text):
        return formats.load(text, self.encoding)

class lists_yaml(lists_json):
    encoding = "yml"
    content_type = "text/yaml"

class list_view_json(delegate.page):
    path = "(/people/[^/]+/lists/OL\d+L)"
    encoding = "json"
    content_type = "application/json"

    def GET(self, key):
        list = web.ctx.site.get(key)
        if not list or list.type.key == '/type/delete':
            raise web.notfound()
        
        data = self.get_list_data(list)
        return delegate.RawText(self.dumps(data))
            
    def get_list_data(self, list):
        return {
            "links": {
                "self": list.key,
                "seeds": list.key + "/seeds",
                "subjects": list.key + "/subjects",
                "editions": list.key + "/editions",
            },
            "name": list.name or None,
            "description": list.description and unicode(list.description) or None,
            "seed_count": len(list.seeds),
            "edition_count": list.edition_count,
            
            "meta": {
                "revision": list.revision,
                "created": list.created.isoformat(),
                "last_modified": list.last_modified.isoformat(),
            }
        }

    def dumps(self, data):
        web.header("Content-Type", self.content_type)
        return formats.dump(data, self.encoding)
    
class list_view_yaml(list_view_json):
    encoding = "yml"
    content_type = "text/yaml"
        
class list_seeds(delegate.page):
    path = "(/people/\w+/lists/OL\d+L)/seeds"
    encoding = "json"
    
    content_type = "application/json"
    
    def GET(self, key):
        list = web.ctx.site.get(key)
        if not list:
            raise web.notfound()
        
        seeds = [seed.dict() for seed in list.get_seeds()]
        
        data = {
            "links": {
                "self": key + "/seeds",
                "list": key
            },
            "size": len(seeds),
            "entries": seeds
        }
        
        text = formats.dump(data, self.encoding)
        return delegate.RawText(text)
        
    def POST(self, key):
        site = web.ctx.site
        
        list = site.get(key)
        if not list:
            raise web.notfound()
            
        if not site.can_write(key):
            raise self.forbidden()
            
        data = formats.load(web.data(), self.encoding)
        
        data.setdefault("add", [])
        data.setdefault("remove", [])
        
        # support /subjects/foo and /books/OL1M along with subject:foo and {"key": "/books/OL1M"}.
        process_seeds = lists_json().process_seeds
        
        for seed in process_seeds(data["add"]):
            list.add_seed(seed)
            
        for seed in process_seeds(data["remove"]):
            list.remove_seed(seed)
            
        seeds = []
        for seed in data["add"] + data["remove"]:
            if isinstance(seed, dict):
                seeds.append(seed['key'])
            else:
                seeds.append(seed)
                
        changeset_data = {
            "list": {"key": key},
            "seeds": seeds,
            "add": data.get("add", []),
            "remove": data.get("remove", [])
        }
            
        d = list._save(comment="updated list seeds.", action="lists", data=changeset_data)
        web.header("Content-Type", self.content_type)
        return delegate.RawText(formats.dump(d, self.encoding))

class list_seed_yaml(list_seeds):
    encoding = "yml"
    content_type = 'text/yaml; charset="utf-8"'
    

class list_editions(delegate.page):
    """Controller for displaying lists of a seed or lists of a person.
    """
    path = "(/people/\w+/lists/OL\d+L)/editions"

    def is_enabled(self):
        return "lists" in web.ctx.features

    def GET(self, path):
        list = web.ctx.site.get(path)
        if not list:
            raise web.notfound()
        
        i = web.input(limit=20, page=1)
        limit = h.safeint(i.limit, 20)
        page = h.safeint(i.page, 1) - 1
        offset = page * limit

        editions = list.get_editions(limit=limit, offset=offset)
        
        list.preload_authors(editions['editions'])
        list.load_changesets(editions['editions'])
        
        return render_template("type/list/editions.html", list, editions)

class list_editions_json(delegate.page):
    path = "(/people/\w+/lists/OL\d+L)/editions"
    encoding = "json"

    content_type = "application/json"

    def GET(self, key):
        list = web.ctx.site.get(key)
        if not list:
            raise web.notfound()
            
        i = web.input(limit=20, offset=0)
        
        limit = h.safeint(i.limit, 20)
        offset = h.safeint(i.offset, 0)

        editions = list.get_editions(limit=limit, offset=offset, _raw=True)
        
        data = make_collection(
            size=editions['count'], 
            entries=[self.process_edition(e) for e in editions['editions']],
            limit=limit,
            offset=offset
        )
        data['links']['list'] = key 
        text = formats.dump(data, self.encoding)
        return delegate.RawText(text, content_type=self.content_type)
        
    def process_edition(self, e):
        e.pop("seeds", None)
        return e
        
class list_editions_yaml(list_editions_json):
    encoding = "yml"
    content_type = 'text/yaml; charset="utf-8"'    
    
def make_collection(size, entries, limit, offset):
    d = {
        "size": size,
        "entries": entries,
        "links": {
            "self": web.changequery(),
        }
    }
    
    if offset + len(entries) < size:
        d['links']['next'] = web.changequery(limit=limit, offset=offset+limit)
    
    if offset:
        d['links']['prev'] = web.changequery(limit=limit, offset=max(0, offset-limit))
    
    return d

class list_subjects_json(delegate.page):
    path = "(/people/\w+/lists/OL\d+L)/subjects"
    encoding = "json"
    content_type = "application/json"

    def GET(self, key):
        list = web.ctx.site.get(key)
        if not list:
            raise web.notfound()
            
        i = web.input(limit=20)
        limit = h.safeint(i.limit, 20)

        data = self.get_subjects(list, limit=limit)
        data['links'] = {
            "self": key + "/subjects",
            "list": key
        }
        
        text = formats.dump(data, self.encoding)
        return delegate.RawText(text, content_type=self.content_type)
        
    def get_subjects(self, list, limit):
        data = list.get_subjects(limit=limit)
        for key, subjects in data.items():
            data[key] = [self._process_subject(s) for s in subjects]
        return dict(data)
        
    def _process_subject(self, s):
        key = s['key']
        if key.startswith("subject:"):
            key = "/subjects/" + web.lstrips(key, "subject:")
        else:
            key = "/subjects/" + key
        return {
            "name": s['name'],
            "count": s['count'],
            "url": key
        }
        
class list_editions_yaml(list_subjects_json):
    encoding = "yml"
    content_type = 'text/yaml; charset="utf-8"'


class export(delegate.page):
    path = "(/people/\w+/lists/OL\d+L)/export"

    def GET(self, key):
        list = web.ctx.site.get(key)
        if not list:
            raise web.notfound()
            
        format = web.input(format="html").format
                
        if format == "html":
            html = render_template("lists/export_as_html", list, self.get_editions(list))
            return delegate.RawText(html)
        elif format == "bibtex":
            html = render_template("lists/export_as_bibtex", list, self.get_editions(list))
            return delegate.RawText(html)
        elif format == "json":
            data = {"editions": self.get_editions(list, raw=True)}
            web.header("Content-Type", "application/json")
            return delegate.RawText(formats.dump_json(data))
        elif format == "yaml":
            data = {"editions": self.get_editions(list, raw=True)}
            web.header("Content-Type", "application/yaml")
            return delegate.RawText(formats.dump_yaml(data))
        else:
            raise web.notfound()
            
    def get_editions(self, list, raw=False):
        editions = list.get_editions(limit=10000, offset=0, _raw=raw)['editions']
        if not raw:
            list.preload_authors(editions)
        return editions
        
class feeds(delegate.page):
    path = "(/people/[^/]+/lists/OL\d+L)/feeds/(updates).(atom)"
    
    def GET(self, key, name, format):
        list = web.ctx.site.get(key)
        if list is None:
            raise web.notfound()
        text = getattr(self, 'GET_' + name + '_' + format)(list)
        return delegate.RawText(text)
    
    def GET_updates_atom(self, list):
        web.header("Content-Type", 'application/atom+xml; charset="utf-8"')
        return render_template("lists/feed_updates.xml", list)
    
def setup():
    pass
    
@public
def get_active_lists_in_random(limit=20):
    # get 5 times more lists and pick the required number in random among them.
    keys = web.ctx.site.things({"type": "/type/list", "sort": "-last_modified", "limit": 5*limit})
    
    # ignore lists with just 1 seed
    lists = [list for list in web.ctx.site.get_many(keys) if len(list.seeds) > 1]
    
    if len(keys) > limit:
        lists = random.sample(lists, limit)
    return lists
