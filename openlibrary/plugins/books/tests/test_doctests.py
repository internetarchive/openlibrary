
import doctest
import py.test

def test_doctest():
    modules = [
        "openlibrary.plugins.books.dynlinks"
    ]
    for t in find_doctests(modules):
        yield run_doctest, t

def find_doctests(modules):
    finder = doctest.DocTestFinder()
    for m in modules:
        mod = __import__(m, None, None, ['x'])
        for t in finder.find(mod, mod.__name__):
            yield t
        
def run_doctest(test):
    runner = doctest.DocTestRunner(verbose=True)
    failures, tries = runner.run(test)
    if failures:
        py.test.fail("doctest failed: " + test.name)
