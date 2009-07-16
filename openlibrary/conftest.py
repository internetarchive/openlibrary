"""py.test configutation for openlibrary
"""
pytest_plugins = ["pytest_doctest"]

def pytest_configure(config):
    #config.option.doctestmodules = True
    return

# till the imports are fixed    
collect_ignore = ["catalog"]
