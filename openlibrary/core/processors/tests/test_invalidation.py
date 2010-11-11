import web
import datetime

from infogami.infobase import client
from openlibrary.core.processors import invalidation
from openlibrary.core.mocksite import MockSite

class MockHook:
    def __init__(self):
        self.call_count = 0
        self.recent_doc = None
        
    def on_new_version(self, doc):
        self.recent_doc = doc
        self.call_count += 1
        
class MockDatetime:
    """Class to mock datetime.datetime to overwrite utcnow method.
    """
    def __init__(self, utcnow):
        self._now = utcnow
    
    def utcnow(self):
        return self._now

class TestInvalidationProcessor:
    def test_hook(self, monkeypatch):
        """When a document is saved, cookie must be set with its timestamp.
        """
        self._monkeypatch_web(monkeypatch)
        
        doc = {
            "key": "/templates/site.tmpl",
            "type": "/type/template"
        }
        web.ctx.site.save(doc, timestamp=datetime.datetime(2010, 01, 01))
        
        hook = invalidation._InvalidationHook("/templates/site.tmpl", cookie_name="invalidation-cookie", expire_time=120)
        hook.on_new_version(web.ctx.site.get(doc['key']))
        
        assert self.cookie == {
            "name": "invalidation-cookie",
            "value": "2010-01-01T00:00:00",
            "expires": 120
        }
        
    def test_reload(self, monkeypatch):
        """If reload is called and there are some modifications, each hook should get called.
        """
        self._monkeypatch_web(monkeypatch)
        self._monkeypatch_hooks(monkeypatch)
        
        # create the processor
        p = invalidation.InvalidationProcessor(prefixes=['/templates/'])
        
        # save a doc after creating the processor
        doc = {
            "key": "/templates/site.tmpl",
            "type": "/type/template"
        }
        web.ctx.site.save(doc)
                
        # reload and make sure the hook gets called
        p.reload()
        
        assert self.hook.call_count == 1
        assert self.hook.recent_doc.dict() == web.ctx.site.get("/templates/site.tmpl").dict()
        
        # last_update_time must get updated
        assert p.last_update_time == web.ctx.site.get("/templates/site.tmpl").last_modified

    def test_reload_on_timeout(self, monkeypatch):
        # create the processor at 60 seconds past in time
        mock_now = datetime.datetime.utcnow() - datetime.timedelta(seconds=60)
        monkeypatch.setattr(datetime, "datetime", MockDatetime(mock_now))
        
        p = invalidation.InvalidationProcessor(prefixes=['/templates'], timeout=60)
        
        # come back to real time
        monkeypatch.undo()

        # monkeypatch web
        self._monkeypatch_web(monkeypatch)
        self._monkeypatch_hooks(monkeypatch)
        
        # save a doc
        doc = {
            "key": "/templates/site.tmpl",
            "type": "/type/template"
        }
        web.ctx.site.save(doc)
                
        # call the processor
        p(lambda: None)
        assert self.hook.call_count == 1
        assert self.hook.recent_doc.dict() == web.ctx.site.get("/templates/site.tmpl").dict()
        
    def test_is_timeout(self, monkeypatch):
        # create the processor at 60 seconds past in time
        mock_now = datetime.datetime.utcnow() - datetime.timedelta(seconds=60)
        monkeypatch.setattr(datetime, "datetime", MockDatetime(mock_now))
        
        p = invalidation.InvalidationProcessor(prefixes=['/templates'], timeout=60)
        
        # come back to real time
        monkeypatch.undo()
        
        # monkeypatch web
        self._monkeypatch_web(monkeypatch)
        self._monkeypatch_hooks(monkeypatch)
        
        p.reload()
        
        # until next 60 seconds, is_timeout must be false.
        assert p.is_timeout() == False
        
    def test_reload_on_cookie(self, monkeypatch):
        self._monkeypatch_web(monkeypatch)
        self._monkeypatch_hooks(monkeypatch)
        
        p = invalidation.InvalidationProcessor(prefixes=['/templates'], cookie_name="invalidation_cookie")
        
        # save a doc
        doc = {
            "key": "/templates/site.tmpl",
            "type": "/type/template"
        }
        web.ctx.site.save(doc)
        
        # call the processor
        p(lambda: None)
        
        # no cookie, no hook call
        assert self.hook.call_count == 0
        
        web.ctx.env['HTTP_COOKIE'] = "invalidation_cookie=" + datetime.datetime.utcnow().isoformat()
        p(lambda: None)
        
        # cookie is set, hook call is expetected
        assert self.hook.call_count == 1
        assert self.hook.recent_doc.dict() == web.ctx.site.get("/templates/site.tmpl").dict()
    
    def test_setcookie_after_reload(self, monkeypatch):
        self._monkeypatch_web(monkeypatch)
        self._monkeypatch_hooks(monkeypatch)
        
        p = invalidation.InvalidationProcessor(prefixes=['/templates'], cookie_name="invalidation_cookie", timeout=60)
        
        # save a doc
        doc = {
            "key": "/templates/site.tmpl",
            "type": "/type/template"
        }
        web.ctx.site.save(doc)
        
        p.reload()
        
        # A cookie must be set when there is a recent update known to the processor
        p(lambda: None)
        
        assert self.cookie == {
            "name": "invalidation_cookie", 
            "expires": p.expire_time, 
            "value": web.ctx.site.get("/templates/site.tmpl").last_modified.isoformat()
        }


    def _load_fake_context(self):
        app = web.application()
        env = {
            'PATH_INFO': '/',
            'HTTP_METHOD': 'GET'
        }
        app.load(env)

    def _monkeypatch_web(self, monkeypatch):
        monkeypatch.setattr(web, "ctx", web.storage(x=1))
        monkeypatch.setattr(web.webapi, "ctx", web.ctx)

        self._load_fake_context()
        web.ctx.site = MockSite()

        def setcookie(name, value, expires):
            self.cookie = dict(name=name, value=value, expires=expires)

        monkeypatch.setattr(web, "setcookie", setcookie)


    def _monkeypatch_hooks(self, monkeypatch):
        self.hook = MockHook()
        monkeypatch.setattr(client, "hooks", [self.hook])
