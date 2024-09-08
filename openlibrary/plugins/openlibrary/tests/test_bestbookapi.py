# from py.test import config
import json

import cookielib
import urllib

from openlibrary.core import models


def pytest_funcarg__config(request):
    return request.config

class RatingsAPI:
    pass
