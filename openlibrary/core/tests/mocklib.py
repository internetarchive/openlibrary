"""Simple mock utility.
"""
import urllib, urllib2
from StringIO import StringIO

class Mock:
    def __init__(self):
        self.calls = []
        self.default = None

    def __call__(self, *a, **kw):
        for a2, kw2, _return in self.calls:
            if (a, kw) == (a2, kw2):
                return _return
        return self.default

    def setup_call(self, *a, **kw):
        _return = kw.pop("_return", None)
        call = a, kw, _return
        self.calls.append(call)

def monkeypatch_urllib(monkeypatch, url, response_string):
    """Monkey-patches urllib.urlopen to return the given response
    when urlopen is called with the given url.
    """
    _urlopen = urllib.urlopen
    given_url = url
    
    def urlopen(url, *a, **kw): 
        if url == given_url:
            return urllib.addinfourl(StringIO(response_string), [], url)
        else:
            return _urlopen(url, *a, **kw)
            
    monkeypatch.setattr(urllib, "urlopen", urlopen)

def monkeypatch_urllib2(monkeypatch, url, response_string):
    """Monkey-patches urllib2.urlopen to return the given response
    when urlopen is called with the given url.
    """
    _urlopen = urllib2.urlopen
    given_url = url

    def urlopen(url, *a, **kw): 
        if url == given_url:
            return urllib.addinfourl(StringIO(response_string), [], url)
        else:
            return _urlopen(url, *a, **kw)

    monkeypatch.setattr(urllib2, "urlopen", urlopen)
