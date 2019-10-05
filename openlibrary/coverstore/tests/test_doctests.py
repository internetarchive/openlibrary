import pytest
from infogami.infobase.tests.test_doctests import find_doctests, run_doctest

modules = [
    'openlibrary.coverstore.archive',
    'openlibrary.coverstore.code',
    'openlibrary.coverstore.db',
    'openlibrary.coverstore.server',
    'openlibrary.coverstore.utils',
    'openlibrary.coverstore.warc',
]

@pytest.mark.parametrize('doctest', find_doctests(modules))
def test_doctests(doctest):
    # dummy function to make py.test think that test belongs in this module instead of run_doctest's module
    run_doctest(doctest)
