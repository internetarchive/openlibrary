from openlibrary.core import ia

def test_xml2dict():
    assert ia.xml2dict("<metadata><x>1</x><y>2</y></metadata>") == {"x": "1", "y": "2"}
    assert ia.xml2dict("<metadata><x>1</x><y>2</y></metadata>", x=[]) == {"x": ["1"], "y": "2"}
    
    assert ia.xml2dict("<metadata><x>1</x><x>2</x></metadata>") == {"x": "2"}
    assert ia.xml2dict("<metadata><x>1</x><x>2</x></metadata>", x=[]) == {"x": ["1", "2"]}