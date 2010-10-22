import web
import datetime

from infogami.infobase import client
from openlibrary.core.processors import invalidation
from openlibrary.core.mocksite import MockSite

class TestInvalidationProcessor:
    def test_hook(self, monkeypatch):
        """When a document is saved, cookie must be set with its timestamp.
        """
        def setcookie(name, value, expires):
            self.cookie = dict(name=name, value=value, expires=expires)

        monkeypatch.setattr(web.ctx, "site", MockSite())
        monkeypatch.setattr(web, "setcookie", setcookie)
        
        doc = {
            "key": "/templates/site.tmpl",
            "type": "/type/template"
        }
        web.ctx.site.save(doc, timestamp=datetime.datetime(2010, 01, 01))
        
        hook = invalidation._InvalidationHook("/templates/site.tmpl", cookie_name="invalidation-cookie", expire_time=120)
        hook.on_new_version(doc)
        
        assert self.cookie == {
            "name": "invalidation-cookie",
            "value": "2010-01-01T00:00:00",
            "expires": 120
        }