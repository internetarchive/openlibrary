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
        doc = web.ctx.site.get(path)
        if not doc:
            raise web.notfound()
            
        i = web.input(offset=0, limit=20)
        i.offset = h.safeint(i.offset, 0)
        i.limit = h.safeint(i.limit, 20)
        
        i.limit = min(i.limit, 100)
        i.offset = max(i.offset, 0)
            
        lists = doc.get_lists(limit=i.limit, offset=i.offset)
        return self.render(doc, lists, i)
    
    def render(self, doc, lists, i):
        d = {
            "links": {
                "self": web.ctx.home + web.ctx.fullpath
            },
            "list_count": len(lists),
            "lists": [{"key": list.key} for list in lists]
        }
        # TODO: add next and prev links        
        return delegate.RawText(self.dumps(d))
        
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
        
        list = user.new_list(
            name=data.get('name', ''),
            description=data.get('description', ''),
            tags=data.get('tags', []),
            seeds=data.get('seeds', [])
        )
        
        try:
            result = site.save(list.dict(), 
                comment="Created new list.",
                action="lists",
                data={
                    "list": {"key": list.key},
                    "seeds": data.get("seeds", [])
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
                
    def get_content_type(self):
        return self.content_type
        
    def dumps(self, data):
        return formats.dump(data, self.encoding)
    
    def loads(self, text):
        return formats.load(text, self.encoding)
        

class lists_yaml(lists_json):
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
        
        data = list.dict().get("seeds", [])
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
        
        for seed in data["add"]:
            list.add_seed(seed)
            
        for seed in data["remove"]:
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

        data = list.get_editions(limit=limit, offset=offset, _raw=True)
        text = formats.dump(data, self.encoding)
        return delegate.RawText(text, content_type=self.content_type)
        
class list_editions_yaml(list_editions_json):
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
    
    if len(keys) > limit:
        keys = random.sample(keys, limit)
    return web.ctx.site.get_many(keys)
