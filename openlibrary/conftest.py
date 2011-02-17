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

def pytest_funcarg__mock_site(request):
    def read_types():
        for path in glob.glob("openlibrary/plugins/openlibrary/types/*.type"):
            text = open(path).read()
            doc = eval(text, dict(true=True, false=False))
            if isinstance(doc, list):
                for d in doc:
                    yield d
            else:
                yield doc
                
    from openlibrary.mocks.mock_infobase import MockSite
    site = MockSite()
    
    for doc in read_types():
        site.save(doc)
    
    return site
    
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

    def finalizer():
        template.disktemplates.clear()
        web.ctx.clear()

    request.addfinalizer(finalizer)
    return render_template