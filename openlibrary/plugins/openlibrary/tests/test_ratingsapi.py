# from py.test import config
import web
import json

import cookielib
import urllib

from openlibrary.plugins.openlibrary.api import ratings
from openlibrary import accounts
from openlibrary.core import models


def pytest_funcarg__config(request):
    return request.config


class RatingsAPI:
    def __init__(self, config):
        self.server = config.getvalue('server')
        self.username = config.getvalue("username")
        self.password = config.getvalue("password")

        self.cookiejar = cookielib.CookieJar()

        self.opener = urllib.request.build_opener()
        self.opener.add_handler(urllib.request.HTTPCookieProcessor(self.cookiejar))

    def urlopen(self, path, data=None, method=None, headers=None):
        headers = headers or {}
        """url open with cookie support."""
        if not method:
            if data:
                method = "POST"
            else:
                method = "GET"

        req = urllib.request.Request(self.server + path, data=data, headers=headers)
        req.get_method = lambda: method
        return self.opener.open(req)

    def login(self):
        data = dict(username=self.username, password=self.password)
        self.urlopen("/account/login", data=urllib.parse.urlencode(data), method="POST")

    def rate_book(self, work_key, data):
        url = '%s/ratings.json' % (work_key)
        headers = {"content-type": "application/json"}
        r = self.urlopen(url, data=json.dumps(data), headers=headers, method="POST")
        return json.loads(r.read())


def test_rating(config, monkeypatch):
    api = RatingsAPI(config)
    api.login()

    work_key = "/works/OL123W"
    data = {"rating": "5"}

    class FakeUser:
        def __init__(self, key):
            self.key = '/users/%s' % key

    monkeypatch.setattr(accounts, "get_current_user", FakeUser('test'))
    monkeypatch.setattr(models.Ratings, "remove", {})
    monkeypatch.setattr(models.Ratings, "add", {})
    result = api.rate_book(work_key, data)
    assert 'success' in result
