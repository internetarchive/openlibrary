"""py.test configutation for openlibrary
"""
import glob

pytest_plugins = ["pytest_unittest"]

from infogami.infobase.tests.pytest_wildcard import pytest_funcarg__wildcard

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
    

    
