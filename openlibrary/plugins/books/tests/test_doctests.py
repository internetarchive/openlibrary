import doctest

import pytest


def find_doctests(modules):
    finder = doctest.DocTestFinder()
    for m in modules:
        mod = __import__(m, None, None, ['x'])
        yield from finder.find(mod, mod.__name__)


@pytest.mark.parametrize('test', find_doctests(["openlibrary.plugins.books.dynlinks"]))
def test_doctest(test):
    runner = doctest.DocTestRunner(verbose=True)
    failures, tries = runner.run(test)
    if failures:
        pytest.fail("doctest failed: " + test.name)
