import os

import pytest
import yaml


@pytest.fixture
def serviceconfig(request):

    root = os.path.dirname(__file__)
    with open(os.path.join(root, "sample_services.yml")) as in_file:
        return yaml.safe_load(in_file)
