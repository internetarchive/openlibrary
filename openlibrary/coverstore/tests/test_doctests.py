import doctest

def run_doctest(modname):
    mod = __import__(modname, None, None, ['x'])
    return doctest.testmod(mod)
    
def test_doctests():
    yield run_doctest, 'openlibrary.coverstore.archive'
    yield run_doctest, 'openlibrary.coverstore.code'
    yield run_doctest, 'openlibrary.coverstore.db'
    yield run_doctest, 'openlibrary.coverstore.server'        
    yield run_doctest, 'openlibrary.coverstore.utils'
    yield run_doctest, 'openlibrary.coverstore.warc'