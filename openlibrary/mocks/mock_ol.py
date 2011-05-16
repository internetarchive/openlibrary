import os
import re
import web
from infogami import config
from infogami.infobase import client
from infogami.utils import delegate

from openlibrary.plugins import ol_infobase

from mock_infobase import pytest_funcarg__mock_site
from _pytest.monkeypatch import pytest_funcarg__monkeypatch

def pytest_funcarg__ol(request):
    """ol funcarg for py.test tests.

    The ol objects exposes the following:
    
        * ol.browser: web.py browser object that works with OL webapp
        * ol.site: mock site (also accessible from web.ctx.site)
        * ol.sentmail: Last mail sent
    """
    return OL(request)
    
@web.memoize
def load_plugins():
    config.plugin_path = ["openlibrary.plugins", ""]
    config.plugins = ["openlibrary", "worksearch", "upstream", "admin"]
    
    delegate._load()
    
class EMail(web.storage):
    def extract_links(self):
        """Extracts link from the email message."""
        return re.findall(r"http://[^\s]*", self.message)

class OL:
    """Mock OL object for all tests.
    """
    def __init__(self, request):
        self.request = request
        
        self.monkeypatch = pytest_funcarg__monkeypatch(request)
        self.site = pytest_funcarg__mock_site(request)
                
        self.monkeypatch.setattr(ol_infobase, "init_plugin", lambda: None)
        
        self._load_plugins(request)
        self._mock_sendmail(request)
        
        self.setup_config()
                
        self.browser = delegate.app.browser()
        
    def setup_config(self):
        config.from_address = "Open Library <noreply@openlibrary.org>"
        
    def _load_plugins(self, request):
        def create_site():
            return self.site
            
        self.monkeypatch.setattr(delegate, "create_site", create_site)
        
        load_plugins()
        
    def _mock_sendmail(self, request):
        self.sentmail = None

        def sendmail(from_address, to_address, subject, message, headers={}, **kw):
            self.sentmail = EMail(kw, 
                from_address=from_address,
                to_address=to_address,
                subject=subject,
                message=message,
                headers=headers)
                
        self.monkeypatch.setattr(web, "sendmail", sendmail)
