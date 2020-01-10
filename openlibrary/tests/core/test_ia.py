from StringIO import StringIO
import urllib2

from openlibrary.core import ia

def test_get_metadata(monkeypatch, mock_memcache):
    metadata_json = """{
        "metadata": {
            "title": "Foo",
            "identifier": "foo00bar",
            "collection": ["printdisabled", "inlibrary"]
        }
    }
    """
    monkeypatch.setattr(urllib2, 'urlopen', lambda url: StringIO(metadata_json))
    assert ia.get_metadata('foo00bar') == {
        "title": "Foo",
        "identifier": "foo00bar",
        "collection": ["printdisabled", "inlibrary"],
        "access-restricted": False,
        "_filenames": []
    }

def test_get_metadata_empty(monkeypatch, mock_memcache):
    monkeypatch.setattr(urllib2, 'urlopen', lambda url: StringIO('{}'))
    assert ia.get_metadata('foo02bar') == {}
