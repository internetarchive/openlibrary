"""Lists implementaion.
"""
import web
import simplejson

from infogami.utils import delegate

class lists_new(delegate.page):
    """Controller for creating new lists.
    """
    path = "(/people/\w+)/lists/new"
    encoding = "json"
    
    def is_enabled(self):
        return "lists" in web.ctx.features
    
    def POST(self, user_key):
        print "lists_new.POST", user_key
        site = web.ctx.site
        user = site.get(user_key)
        
        if not user:
            raise web.notfound()
        
        data = simplejson.loads(web.data())
        # TODO: validate data
        
        list = user.new_list(
            name=data['name'], 
            description=data.get('description', ''),
            tags=data.get('tags', []),
            members=data.get('members', [])
        )
        
        result = site.save(list.dict(), 
            comment="Created new list.",
            action="new-list"
        )
        web.header("Content-Type", "application/json")
        return delegate.RawText(result)
        
def setup():
    pass