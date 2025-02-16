import pytest


@pytest.fixture
def serviceconfig(request):
    import os

    import yaml

    root = os.path.dirname(__file__)
    with open(os.path.join(root, "sample_services.yml")) as in_file:
        return yaml.safe_load(in_file)
