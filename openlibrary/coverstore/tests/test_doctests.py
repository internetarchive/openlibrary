from infogami.infobase.tests.test_doctests import find_doctests, run_doctest

def test_doctests():
    modules = [
        'openlibrary.coverstore.archive',
        'openlibrary.coverstore.code',
        'openlibrary.coverstore.db',
        'openlibrary.coverstore.server',
        'openlibrary.coverstore.utils',
        'openlibrary.coverstore.warc',
    ]
    for t in find_doctests(modules):
        yield _run_doctest, t

def _run_doctest(t):
    # dummy function to make py.test think that test belongs in this module instead of run_doctest's module
    run_doctest(t)