from openlibrary.core import ia

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
