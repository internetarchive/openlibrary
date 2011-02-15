from ..solr import Solr

def test_prepare_select():
    solr = Solr("http://localhost:8983/solr")
    assert solr._prepare_select("foo") == "foo"
        
    assert solr._prepare_select({"isbn": "1234567890"}) == 'isbn:"1234567890"'
    assert solr._prepare_select({"isbn": ["1234567890", "9876543210"]}) == 'isbn:("1234567890" OR "9876543210")'
    
    assert solr._prepare_select({"publish_year": ("1990", "2000")}) == 'publish_year:[1990 TO 2000]'