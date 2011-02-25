"""py.test configutation for openlibrary
"""
import glob

import web

from infogami.infobase.tests.pytest_wildcard import pytest_funcarg__wildcard
from infogami.utils import template
from infogami.utils.view import render_template
from openlibrary.i18n import gettext
from openlibrary.core import helpers

pytest_plugins = ["pytest_unittest"]

from openlibrary.mocks.mock_infobase import pytest_funcarg__mock_site
from openlibrary.mocks.mock_ia import pytest_funcarg__mock_ia
from openlibrary.mocks.mock_memcache import pytest_funcarg__mock_memcache

def pytest_funcarg__render_template(request):
    """Utility to test templates.
    """    
    template.load_templates("openlibrary/plugins/openlibrary")
    template.load_templates("openlibrary/plugins/upstream")
    
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
        d = render_template(name, *a, **kw)
        if as_string:
            return unicode(d)
        else:
            return d
    return render