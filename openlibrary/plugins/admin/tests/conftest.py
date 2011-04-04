def pytest_funcarg__serviceconfig(request):
    import yaml
    f = open("tests/sample_services.yml")
    d = yaml.load(f)
    f.close()
    return d
