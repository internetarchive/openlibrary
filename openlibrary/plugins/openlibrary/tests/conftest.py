collect_ignore = ['test_listapi.py']

def pytest_addoption(parser):
    parser.addoption("--server", default=None)
    parser.addoption("--username")
    parser.addoption("--password")

def pytest_configure(config):
    print "pytest_configure", config.getvalue("server")

    if config.getvalue("server"):
        collect_ignore[:] = []

