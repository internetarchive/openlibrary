# from py.test import config
import web
import json

import cookielib

import urllib


def pytest_funcarg__config(request):
    return request.config


class ListAPI:
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
        print(self.cookiejar)

    def create_list(self, data):
        json_data = json.dumps(data)
        headers = {"content-type": "application/json"}
        response = self.urlopen(
            "/people/" + self.username + "/lists", data=json_data, headers=headers
        )
        return json.loads(response.read())

    def get_lists(self):
        data = self.urlopen("/people/" + self.username + "/lists.json").read()
        return json.loads(data)

    def get_list(self, key):
        data = self.urlopen(key + ".json").read()
        return json.loads(data)

    def get_seeds(self, key):
        data = self.urlopen(key + "/seeds.json").read()
        return json.loads(data)

    def update_seeds(self, key, additions, removals):
        data = {
            "add": additions,
            "remove": removals,
        }
        json_data = json.dumps(data)
        response = self.urlopen(key + "/seeds.json", json_data)
        return json.loads(response.read())


def test_create(config):
    api = ListAPI(config)
    api.login()

    data = {
        "name": "foo",
        "description": "foo bar",
        "tags": ["t1", "t2"],
        "seeds": ["subject:cheese"],
    }
    result = api.create_list(data)
    assert "key" in result and result['revision'] == 1
    list_key = result['key']

    # test get
    list = api.get_list(list_key)
    for k in ["created", "last_modified"]:
        list.pop(k)

    assert list == {
        "key": result['key'],
        "type": {"key": "/type/list"},
        "revision": 1,
        "latest_revision": 1,
        "name": "foo",
        "description": {"type": "/type/text", "value": "foo bar"},
        "tags": ["t1", "t2"],
        "seeds": ["subject:cheese"],
    }

    # test get seeds
    assert api.get_seeds(list_key) == ["subject:cheese"]


def test_add_seeds(config):
    api = ListAPI(config)
    api.login()

    data = {
        "name": "foo",
        "description": "foo bar",
        "tags": ["t1", "t2"],
        "seeds": ["subject:cheese"],
    }
    result = api.create_list(data)
    key = result['key']

    # remove cheese and add apple
    api.update_seeds(key, ["subject:apple"], ["subject:cheese"])
    assert api.get_seeds(key) == ["subject:apple"]


def test_lists(config):
    api = ListAPI(config)
    api.login()

    count = api.get_lists()['list_count']

    api.create_list({"name": "foo"})

    new_count = api.get_lists()['list_count']
    # counts are not accurate yet.
    # assert new_count == count + 1
