import doctest

def test_doctest():
    modules = [
        "openlibrary.plugins.openlibrary.processors"
    ]
    for name in modules:
        mod = __import__(name, None, None, ['x'])
        yield do_doctest, mod

def do_doctest(mod):
    doctest.testmod(mod)
        

