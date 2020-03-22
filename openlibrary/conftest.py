"""pytest configutation for openlibrary
"""
import glob
import pytest
# import web

import six

from infogami.infobase.tests.pytest_wildcard import Wildcard
from infogami.utils import template
# from infogami.utils.view import render_template as infobase_render_template
from openlibrary.i18n import gettext
# from openlibrary.core import helpers

from openlibrary.mocks.mock_infobase import mock_site
from openlibrary.mocks.mock_ia import mock_ia
from openlibrary.mocks.mock_memcache import mock_memcache
# from openlibrary.mocks.mock_ol import ol

# TODO (cclauss): Undo Python 2 workaround for vendoring in an out-of-date infogami
import web
web.utf8 = web.safestr
from infogami.utils.view import render_template as infobase_render_template  # noqa: F401
from openlibrary.core import helpers  # noqa: F401
from openlibrary.mocks.mock_ol import ol  # noqa: F401



@pytest.fixture(autouse=True)
def no_requests(monkeypatch):
    def mock_request(*args, **kwargs):
        raise Warning('Network requests are blocked in the testing environment')
    monkeypatch.setattr("requests.sessions.Session.request", mock_request)

@pytest.fixture
def wildcard():
    return Wildcard()

@pytest.fixture
def render_template(request):
    """Utility to test templates.
    """
    template.load_templates("openlibrary")

    #TODO: call setup on upstream and openlibrary plugins to
    # load all globals.
    web.template.Template.globals["_"] = gettext
    web.template.Template.globals.update(helpers.helpers)

    web.ctx.env = web.storage()
    web.ctx.headers = []
    web.ctx.lang = "en"

    # ol_infobase.init_plugin call is failing when trying to import plugins.openlibrary.code.
    # monkeypatch to avoid that.
    from openlibrary.plugins import ol_infobase

    init_plugin = ol_infobase.init_plugin
    ol_infobase.init_plugin = lambda: None
    def undo():
        ol_infobase.init_plugin = init_plugin
    request.addfinalizer(undo)

    from openlibrary.plugins.openlibrary import code
    web.config.db_parameters = dict()
    code.setup_template_globals()

    def finalizer():
        template.disktemplates.clear()
        web.ctx.clear()

    request.addfinalizer(finalizer)

    def render(name, *a, **kw):
        as_string = kw.pop("as_string", True)
        d = infobase_render_template(name, *a, **kw)
        return six.text_type(d) if as_string else d
    return render
