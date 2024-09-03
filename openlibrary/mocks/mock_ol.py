import pytest
import re
import web
from infogami import config
from infogami.utils import delegate

try:  # newer versions of web.py
    from web.browser import AppBrowser
except ImportError:  # older versions of web.py
    from web import AppBrowser

from openlibrary.mocks.mock_infobase import mock_site, MockConnection
from openlibrary.plugins import ol_infobase


@pytest.fixture
def ol(request):
    """ol funcarg for pytest tests.

    The ol objects exposes the following:

        * ol.browser(): web.py browser object that works with OL webapp
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


class OLBrowser(AppBrowser):
    def get_text(self, e=None, name=None, **kw):
        if name or kw:
            e = self.get_soup().find(name=name, **kw)
        return AppBrowser.get_text(self, e)


class OL:
    """Mock OL object for all tests."""

    @pytest.fixture
    def __init__(self, request, monkeypatch):
        self.request = request

        self.monkeypatch = monkeypatch(request)
        self.site = mock_site(request)

        self.monkeypatch.setattr(ol_infobase, "init_plugin", lambda: None)

        self._load_plugins(request)
        self._mock_sendmail(request)

        self.setup_config()

    def browser(self):
        return OLBrowser(delegate.app)

    def setup_config(self):
        config.from_address = "Open Library <noreply@openlibrary.org>"

    def _load_plugins(self, request):
        def create_site():
            web.ctx.conn = MockConnection()

            if web.ctx.get('env'):
                auth_token = web.cookies().get(config.login_cookie_name)
                web.ctx.conn.set_auth_token(auth_token)
            return self.site

        self.monkeypatch.setattr(delegate, "create_site", create_site)

        load_plugins()

    def _mock_sendmail(self, request):
        self.sentmail = None

        def sendmail(from_address, to_address, subject, message, headers=None, **kw):
            headers = headers or {}
            self.sentmail = EMail(
                kw,
                from_address=from_address,
                to_address=to_address,
                subject=subject,
                message=message,
                headers=headers,
            )

        self.monkeypatch.setattr(web, "sendmail", sendmail)
