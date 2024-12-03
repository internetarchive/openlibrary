import doctest

import pytest

modules = [
    'openlibrary.coverstore.archive',
    'openlibrary.coverstore.code',
    'openlibrary.coverstore.db',
    'openlibrary.coverstore.server',
    'openlibrary.coverstore.utils',
]


@pytest.mark.parametrize('module', modules)
def test_doctest(module):
    mod = __import__(module, None, None, ['x'])
    finder = doctest.DocTestFinder()
    tests = finder.find(mod, mod.__name__)
    print(f"Doctests found in {module}: {[len(m.examples) for m in tests]}\n")
    for test in tests:
        runner = doctest.DocTestRunner(verbose=True)
        failures, tries = runner.run(test)
        if failures:
            pytest.fail("doctest failed: " + test.name)
