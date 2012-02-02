import pytest


from ..functions import doc_to_things, search, create, thing_to_doc, things_to_matches, find_matches_by_isbn, find_matches_by_identifiers, find_matches_by_title_and_publishers, massage_search_results


def populate_infobase(site):
    "Dumps some documents into infobase"
    ## Create two authors
    atype = '/type/author'
    akey0 = site.new_key(atype)
    a0 = {'name'         : 'Test author 1',
          'type'         : {'key': atype},
          'key'          : akey0}
    
    akey1 = site.new_key(atype)
    a1 = {'name'         : 'Test author 1',
          'type'         : {'key': atype},
          'key'          : akey1}
    
    
    ## Create a work
    wtype = '/type/work'
    wkey = site.new_key(wtype)
    w = { 
        'title'        : 'test1',
        'type'         : {'key': wtype},
        'key'          : wkey,
        'authors'      : [ {'author' : a0}, {'author' : a1}]
        }
    site.save(w)    
    
    ## Create two editions for this work
    editions = []
    etype = '/type/edition'
    for i in range(2):
        ekey = site.new_key(etype)
        e = {
            'title'        : 'test1',
            'type'         : {'key': etype},
            'lccn'         : ['123%d'%i],
            'oclc_numbers' : ['456%d'%i],
            'key'          : ekey,
            'ocaid'        : "12345%d"%i,
            'isbn_10'      : ["123456789%d"%i],
            "works"        : [{ "key": wkey }]
            }
        site.save(e)
        editions.append(ekey)
        
    ## Now create a work without any edition
    wkey = site.new_key(wtype)
    w = {
        'title'        : 'editionless',
        'type'         : {'key': wtype},
        'key'          : wkey,
        }
    site.save(w)
    
    

def test_doc_to_thing_adds_key_to_edition(mock_site):
    "Test whether doc_to_things adds a key to an edition"
    doc = {'type' : '/type/edition'}
    thing = doc_to_things(doc)
    assert 'key' in thing[0]
    assert thing[0]['key'] == '/books/OL1M'

def test_doc_to_thing_adds_key_to_work(mock_site):
    "Test whether doc_to_things adds a key to a work"
    doc = {'type' : '/type/work'}
    thing = doc_to_things(doc)
    assert 'key' in thing[0]
    assert thing[0]['key'] == '/works/OL1W'

def test_doc_to_thing_adds_key_to_author(mock_site):
    "Test whether doc_to_things adds a key to an author"
    doc = {'type' : '/type/author'}
    thing = doc_to_things(doc)
    assert 'key' in thing[0]
    assert thing[0]['key'] == '/authors/OL1A'

def test_doc_to_thing_updation_of_edition(mock_site):
    "Tests whether edition records are populated with fields from the database"
    populate_infobase(mock_site)
    doc = {'type' : '/type/edition', 'key' : '/books/OL1M'}
    thing = doc_to_things(doc)
    expected = {'title': 'test1',
                'lccn': ['1230'],
                'isbn_10': ['1234567890'],
                'key': '/books/OL1M',
                'ocaid': '123450',
                'oclc_numbers': ['4560'],
                'works': [mock_site.get('/works/OL1W')],
                'type': mock_site.get('/type/edition')}
    assert thing[0] == expected

def test_doc_to_thing_updation_of_work(mock_site):
    "Tests whether work records are populated with fields from the database"
    populate_infobase(mock_site)
    doc = {'type' : '/type/work', 'key' : '/works/OL1W'}
    thing = doc_to_things(doc)
    authors = thing[0].pop('authors')
    expected = {'type': mock_site.get('/type/work'), 'key': '/works/OL1W', 'title': 'test1'}
    assert thing[0] == expected
    assert set(i.author.key for i in authors) == set(['/authors/OL1A', '/authors/OL2A'])

def test_doc_to_thing_unpack_work_and_authors_from_edition(mock_site):
    "Tests if the 'work' and 'author' fields in a an edition doc are unpacked and converted."
    doc = {'type' : '/type/edition', 
           'work' : { 'title' : 'Test title for work'},
           'authors' : [ {'name' : 'Test author'} ]
           }
    things = doc_to_things(doc)
    expected = [{'key': '/books/OL1M', 'type': '/type/edition'}, # The edition
                
                {'authors': [{'author': '/authors/OL1A', 'type': '/type/author_role'}],
                 'key': '/works/OL1W',
                 'title': 'Test title for work',
                 'type': '/type/work'}, # The work
                
                {'key': '/authors/OL1A', 'name': 'Test author', 'type': '/type/author'} # The author
                ]
    assert expected  == things

def test_doc_to_thing_unpack_authors_from_work(mock_site):
    "Tests if the 'authors' fields in a work doc are unpacked and converted."
    doc = {'type' : '/type/work', 
           'title' : 'This is a test book',
           'authors' : [ {'name' : 'Test author'} ]
           }
    things = doc_to_things(doc)
    expected = [                
                {'authors': [{'author': '/authors/OL1A', 'type': '/type/author_role'}],
                 'key': '/works/OL1W',
                 'title': 'This is a test book',
                 'type': '/type/work'}, # The work
                
                {'key': '/authors/OL1A', 'name': 'Test author', 'type': '/type/author'} # The author
                ]
    assert expected  == things

def test_doc_to_thing_unpack_identifiers(mock_site):
    "Tests if the identifiers are unpacked from an edition"
    doc = {'type' : '/type/edition', 
           'identifiers' : {"oclc_numbers" : ['1234'],
                            "isbn_10" : ['1234567890'],
                            "isbn_13" : ['1234567890123'],
                            "lccn" : ['5678'],
                            "ocaid" : ['90']}}
    things = doc_to_things(doc)
    for k,v in doc['identifiers'].iteritems():
        assert things[0][k] == v



def test_create(mock_site):
    "Tests the create API"
    doc = {'type' : '/type/edition', 
           'publisher' : "Test publisher",
           'work' : { 'title' : 'Test title for work'},
           'authors' : [{'name' : 'Test author'}],
           'identifiers' : {"oclc_numbers" : ['1234'],
                            "isbn_10" : ['1234567890'],
                            "isbn_13" : ['1234567890123'],
                            "lccn" : ['5678'],
                            "ocaid" : ['90']}}
    create({'doc' : doc})
    work = mock_site.get("/works/OL1W")
    edition = mock_site.get("/books/OL1M")
    author = mock_site.get("/authors/OL1A")
    # Check work
    assert work.title == "Test title for work"
    assert len(work.authors) == 1
    assert work.authors[0].author == "/authors/OL1A"
    # Check edition
    for k,v in doc['identifiers'].iteritems():
        assert edition[k] == v
    edition.publisher = "Test publisher"
    # Check author
    assert author.name == "Test author"

def test_thing_to_doc_edition(mock_site):
    "Tests whether an edition is properly converted back into a doc"
    populate_infobase(mock_site)
    edition = mock_site.get('/books/OL1M')
    doc = thing_to_doc(edition)
    expected = {'authors': [{'key': '/authors/OL1A'}, {'key': '/authors/OL2A'}],
                'identifiers': {'isbn': ['1234567890'],
                                'lccn': ['1230'],
                                'ocaid': '123450',
                                'oclc_numbers': ['4560']},
                'key': '/books/OL1M',
                'title': 'test1',
                'type': u'/type/edition',
                'work': {'key': u'/works/OL1W'}}
    assert doc == expected

def test_thing_to_doc_edition_key_limiting(mock_site):
    "Tests whether extra keys are removed during converting an edition into a doc"
    populate_infobase(mock_site)
    edition = mock_site.get('/books/OL1M')
    doc = thing_to_doc(edition, ["title"])
    expected = {'authors': [{'key': '/authors/OL1A'}, {'key': '/authors/OL2A'}],
                'key': '/books/OL1M',
                'title': 'test1',
                'type': u'/type/edition',
                'work': {'key': u'/works/OL1W'}}
    assert doc == expected


def test_thing_to_doc_work(mock_site):
    "Tests whether a work is properly converted back into a doc"
    populate_infobase(mock_site)
    edition = mock_site.get('/works/OL1W')
    doc = thing_to_doc(edition)
    expected = {'authors': [{'key': '/authors/OL1A'}, {'key': '/authors/OL2A'}],
                'key': '/works/OL1W',
                'title': 'test1',
                'type': u'/type/work'}
    assert doc == expected

def test_things_to_matches(mock_site):
    """Tests whether a list of keys is converted into a list of
    'matches' as returned by the search API"""
    populate_infobase(mock_site)
    matches = things_to_matches(['/books/OL1M', '/works/OL2W'])
    expected = [{'edition': '/books/OL1M', 'work': u'/works/OL1W'},
                {'edition': None, 'work': '/works/OL2W'}]
    assert matches == expected

@pytest.mark.skipif('"isbn_ not supported by mock_site"')
def test_find_matches_by_isbn(mock_site):
    """Tests whether books are matched by ISBN"""
    populate_infobase(mock_site)
    matches = find_matches_by_isbn(['1234567890'])
    assert matches == ['/books/OL1M']

def test_find_matches_by_identifiers(mock_site):
    "Validates the all and any return values of find_matches_by_identifiers"
    # First create 2 records
    record0 = {'doc': {'identifiers' : {"oclc_numbers" : ["1807182"],
                                        "lccn": [ "34029558"],
                                        'isbn_10': ['1234567890']},
                      'key': None,
                      'title': 'THIS IS A TEST BOOK 1',
                      'type': '/type/edition'}}

    record1 = {'doc': {'identifiers' : {"oclc_numbers" : ["2817081"],
                                        "lccn": [ "34029558"],
                                        'isbn_10': ['09876543210']},
                       'key': None,
                       'title': 'THIS IS A TEST BOOK 2',
                       'type': '/type/edition'}}
    
    create(record0)
    create(record1)

    q = {'oclc_numbers': "1807182", 'lccn': '34029558'}
                              
    results = find_matches_by_identifiers(q)

    assert results["all"] == ['/books/OL1M']
    assert results["any"] == ['/books/OL1M', '/books/OL2M']

def test_find_matches_by_title_and_publishers(mock_site):
    "Try to search for a record that should match by publisher and year of publishing"
    record0 = {'doc': {'isbn_10': ['1234567890'],
                       'key': None,
                       'title': 'Bantam book',
                       'type': '/type/edition',
                       'publishers' : ['Bantam'],
                       'publish_year': '1992'}}

    record1 = {'doc': {'isbn_10': ['0987654321'],
                       'key': None,
                       'title': 'Dover book',
                       'type': '/type/edition',
                       'publishers' : ['Dover'],
                       'publish_year': '2000'}}
               

    create(record0)
    create(record1)
    
    # A search that should fail
    q = {'publishers': ["Bantam"], 
         'publish_year': '2000'}
    result = find_matches_by_title_and_publishers(q)
    assert not result, "Found a match '%s' where there should have been none"%result

    # A search that should return the first entry (title, publisher and year)
    q = {'title': 'Bantam book',
         'publishers': ["Bantam"], 
         'publish_year': '1992'}
    result = find_matches_by_title_and_publishers(q)
    assert result == ['/books/OL1M']

    # A search that should return the second entry (title only)
    q = {'title': 'Dover book'}
    result = find_matches_by_title_and_publishers(q)
    assert result == ['/books/OL2M']
    # TODO: Search by title and then filter for publisher in the application directly.

    
def test_search_by_title(mock_site):
    "Drill the main search API using title"
    populate_infobase(mock_site)
    q = {'title' : "test1"}
    matches = search({"doc" : q})
    expected = {'doc': {'authors': [{'key': '/authors/OL1A'}, {'key': '/authors/OL2A'}],
                        'key': '/books/OL1M',
                        'title': 'test1',
                        'type': u'/type/edition',
                        'work': {'key': u'/works/OL1W'}},
                'matches': [{'edition': '/books/OL1M', 'work': u'/works/OL1W'},
                            {'edition': '/books/OL2M', 'work': u'/works/OL1W'}]}
    assert matches == expected

    
@pytest.mark.skipif('"isbn_ not supported by mock_site"')
def test_search_by_isbn(mock_site):
    "Drill the main search API using isbn"
    populate_infobase(mock_site)
    q = ['1234567890']
    matches = search({"doc" : {"identifiers" : {"isbn" : q}}})
    assert matches == {'doc': {'authors': [{'key': '/authors/OL1A'}, {'key': '/authors/OL2A'}],
                               'identifiers': {'isbn': ['1234567890'],
                                               'lccn': ['1230'],
                                               'ocaid': '123450',
                                               'oclc_numbers': ['4560']},
                               'key': '/books/OL1M',
                               'title': 'test1',
                               'type': u'/type/edition',
                               'work': {'key': u'/works/OL1W'}},
                       'matches': [{'edition': '/books/OL1M', 'work': u'/works/OL1W'}]}


def test_massage_search_results_edition(mock_site):
    "Test if search results are properly massaged"
    populate_infobase(mock_site)
    matches = ['/books/OL1M', '/books/OL2M']
    # With limiting
    massaged = massage_search_results(matches, ["title"])
    expected = {'doc': {'authors': [{'key': '/authors/OL1A'}, {'key': '/authors/OL2A'}],
                        'key': '/books/OL1M',
                        'title': 'test1',
                        'type': u'/type/edition',
                        'work': {'key': u'/works/OL1W'}},
                'matches': [{'edition': '/books/OL1M', 'work': u'/works/OL1W'},
                            {'edition': '/books/OL2M', 'work': u'/works/OL1W'}]}
    assert massaged == expected
    
    # Without limiting
    massaged = massage_search_results(matches)
    expected = {'doc': {'authors': [{'key': '/authors/OL1A'}, {'key': '/authors/OL2A'}],
                        'identifiers': {'isbn': ['1234567890'],
                                        'lccn': ['1230'],
                                        'ocaid': '123450',
                                        'oclc_numbers': ['4560']},
                        'key': '/books/OL1M',
                        'title': 'test1',
                        'type': u'/type/edition',
                        'work': {'key': u'/works/OL1W'}},
                'matches': [{'edition': '/books/OL1M', 'work': u'/works/OL1W'},
                            {'edition': '/books/OL2M', 'work': u'/works/OL1W'}]}
    assert massaged == expected
    
#TODO : Test when no matches at all are found
    
