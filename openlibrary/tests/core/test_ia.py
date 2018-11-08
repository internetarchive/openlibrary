from __future__ import print_function
from openlibrary.core import ia

def test_xml2dict():
    assert ia.xml2dict("<metadata><x>1</x><y>2</y></metadata>") == {"x": "1", "y": "2"}
    assert ia.xml2dict("<metadata><x>1</x><y>2</y></metadata>", x=[]) == {"x": ["1"], "y": "2"}

    assert ia.xml2dict("<metadata><x>1</x><x>2</x></metadata>") == {"x": "2"}
    assert ia.xml2dict("<metadata><x>1</x><x>2</x></metadata>", x=[]) == {"x": ["1", "2"]}

def test_get_metaxml(monkeypatch, mock_memcache):
    import StringIO
    import urllib2

    metadata_json = None
    def urlopen(url):
        return StringIO.StringIO(metadata_json)

    monkeypatch.setattr(urllib2, "urlopen", urlopen)

    # test with correct xml
    metadata_json = """{
        "metadata": {
            "title": "Foo",
            "identifier": "foo00bar",
            "collection": ["printdisabled", "inlibrary"]
        }
    }
    """

    print(ia.get_meta_xml("foo00bar"))
    assert ia.get_meta_xml("foo00bar") == {
        "title": "Foo",
        "identifier": "foo00bar",
        "collection": ["printdisabled", "inlibrary"],
        "access-restricted": False,
        "_filenames": []
    }

    # test with metadata errors
    metadata_json = "{}"
    assert ia.get_meta_xml("foo02bar") == {}
