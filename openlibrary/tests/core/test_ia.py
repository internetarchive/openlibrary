from openlibrary.core import ia

def test_get_metadata(monkeypatch, mock_memcache):
    metadata = {
        "metadata": {
            "title": "Foo",
            "identifier": "foo00bar",
            "collection": ["printdisabled", "inlibrary"]
        }
    }

    monkeypatch.setattr(ia, 'get_api_response', lambda *args: metadata)
    assert ia.get_metadata('foo00bar') == {
        "title": "Foo",
        "identifier": "foo00bar",
        "collection": ["printdisabled", "inlibrary"],
        "access-restricted": False,
        "_filenames": []
    }

def test_get_metadata_empty(monkeypatch, mock_memcache):
    monkeypatch.setattr(ia, 'get_api_response', lambda *args: {})
    assert ia.get_metadata('foo02bar') == {}
