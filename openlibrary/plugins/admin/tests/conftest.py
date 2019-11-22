import pytest


@pytest.fixture
def serviceconfig(request):
    import os
    import yaml

    root = os.path.dirname(__file__)
    f = open(os.path.join(root, "sample_services.yml"))
    d = yaml.load(f)
    f.close()
    return d
