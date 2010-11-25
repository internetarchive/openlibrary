"""Lists implementaion.
"""
import web
import simplejson
import yaml

from infogami.utils import delegate
from infogami.utils.view import render_template
from infogami.infobase import client

from openlibrary.core import formats
import openlibrary.core.helpers as h

class lists(delegate.page):
    """Controller for displaying lists of a seed or lists of a person.
    """
    path = "(/(?:people|books|works|authors|subjects)/\w+)/lists"

    def is_enabled(self):
        return "lists" in web.ctx.features
            
    def GET(self, path):
        doc = web.ctx.site.get(path)
        if not doc:
            raise web.notfound()
            
        lists = doc.get_lists()
        return self.render(doc, lists)
        
    def render(self, doc, lists):
        return render_template("lists/lists.html", doc, lists)
        
class lists_json(delegate.page):
    path = "(/(?:people|books|works|authors|subjects)/\w+)/lists"
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
                action="new-list"
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
        
        for seed in data.get("add", []):
            list.add_seed(seed)
            
        for seed in data.get("remove", []):
            list.remove_seed(seed)
            
        d = list._save(comment="updated list seeds.")

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
            
        i = web.input(format="html")
        editions = list.get_editions(limit=10000, offset=0, _raw=True)['editions']
        
        if i.format == "html":
            return render_template("lists/export_as_html", list, editions)
        elif i.format == "json":
            web.header("Content-Type", "application/json")
            return delegate.RawText(formats.dump_json({"editions": editions}))
        elif i.format == "yaml":
            web.header("Content-Type", "application/yaml")
            return delegate.RawText(formats.dump_yaml({"editions": editions}))
        else:
            # TODO: show error 
            pass

def setup():
    pass