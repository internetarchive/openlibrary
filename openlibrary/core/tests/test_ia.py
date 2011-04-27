from openlibrary.core import ia

def test_xml2dict():
    assert ia.xml2dict("<metadata><x>1</x><y>2</y></metadata>") == {"x": "1", "y": "2"}
    assert ia.xml2dict("<metadata><x>1</x><y>2</y></metadata>", x=[]) == {"x": ["1"], "y": "2"}
    
    assert ia.xml2dict("<metadata><x>1</x><x>2</x></metadata>") == {"x": "2"}
    assert ia.xml2dict("<metadata><x>1</x><x>2</x></metadata>", x=[]) == {"x": ["1", "2"]}
    
def test_get_metaxml(monkeypatch, mock_memcache):
    import StringIO
    import urllib2
    
    metaxml = None
    def urlopen(url):
        return StringIO.StringIO(metaxml)
    
    monkeypatch.setattr(urllib2, "urlopen", urlopen)
    
    
    # test with correct xml
    metaxml = """<?xml version="1.0" encoding="UTF-8"?>
    <metadata>
        <title>Foo</title>
        <identifier>foo00bar</identifier>
        <collection>printdisabled</collection>
        <collection>inlibrary</collection>
    </metadata>
    """
    
    assert ia.get_meta_xml("foo00bar") == {
        "title": "Foo", 
        "identifier": "foo00bar",
        "collection": ["printdisabled", "inlibrary"],
        'external-identifier': [],
    }
    
    # test with html errors
    metaxml = """<html>\n<head>\n <title>Internet Archive: Error</title>..."""
    assert ia.get_meta_xml("foo01bar") == {}
    
    # test with bad xml
    metaxml = """<?xml version="1.0" encoding="UTF-8"?>
    <metadata>
        <title>Foo</title>
        <identifier>foo00bar
    """
    assert ia.get_meta_xml("foo02bar") == {}