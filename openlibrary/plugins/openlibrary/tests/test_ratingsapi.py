from py.test import config
import web
import simplejson

import urllib, urllib2
import cookielib

def pytest_funcarg__config(request):
    return request.config

class RatingsAPI:
    def __init__(self, config):
        self.server = config.getvalue('server')
        self.username = config.getvalue("username")
        self.password = config.getvalue("password")

        self.cookiejar = cookielib.CookieJar()

        self.opener = urllib2.build_opener()
        self.opener.add_handler(
            urllib2.HTTPCookieProcessor(self.cookiejar))

    def urlopen(self, path, data=None, method=None, headers={}):
        """url open with cookie support."""
        if not method:
            if data:
                method = "POST"
            else:
                method = "GET"

        req = urllib2.Request(self.server + path, data=data, headers=headers)
        req.get_method = lambda: method
        return self.opener.open(req)

    def login(self):
        data = dict(username=self.username, password=self.password)
        self.urlopen("/account/login", data=urllib.urlencode(data), method="POST")
        print self.cookiejar


    def rate_book(self, work, data):
        json = simplejson.dumps(data)
        headers = {
            "content-type": "application/json"
        }
        url = work

        # mock

        response = self.urlopen(
            "%s/widget" % work,
            data=json,
            headers=headers)
        return simplejson.loads(response.read())


def test_rating(config):
    api = RatingsAPI(config)
    api.login()

    work = "/works/OL123W"
    data = {
        "key": work,
        "rating": "5"
    }
    result = api.rate_book(work, data)
    assert 'success' in msg
