# from py.test import config
import json

import requests

from openlibrary import accounts
from openlibrary.core import models


def pytest_funcarg__config(request):
    return request.config


class RatingsAPI:
    def __init__(self, config):
        self.server = config.getvalue("server")
        self.username = config.getvalue("username")
        self.password = config.getvalue("password")
        self.session = requests.Session()

    def urlopen(self, path, data=None, method=None, headers=None):
        headers = headers or {}
        """url open with cookie support."""
        if not method:
            if data:
                method = "POST"
            else:
                method = "GET"
        req = requests.Request(method, self.server + path, data=data, headers=headers)
        return self.session.send(req)

    def login(self):
        data = {"username": self.username, "password": self.password}
        self.urlopen("/account/login", data=data, method="POST")

    def rate_book(self, work_key, data):
        url = "%s/ratings.json" % (work_key)
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
            self.key = "/users/%s" % key

    monkeypatch.setattr(accounts, "get_current_user", FakeUser("test"))
    monkeypatch.setattr(models.Ratings, "remove", {})
    monkeypatch.setattr(models.Ratings, "add", {})
    result = api.rate_book(work_key, data)
    assert "success" in result
