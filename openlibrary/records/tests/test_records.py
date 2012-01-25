"""
Tests for the records package.
"""

from ..functions import search, create, massage_search_results, find_matches_by_identifiers


def test_massage_search_results(mock_site):
    "Test the function to massage search results into the proper response format"
    # Setup
    ## Create a work
    wtype = '/type/work'
    wkey = mock_site.new_key(wtype)
    w = { #TODO: Add author information here
        'title'        : 'test1',
        'type'         : {'key': wtype},
        'key'          : wkey,
        }
    mock_site.save(w)    

    ## Create two editions for this work
    editions = []
    etype = '/type/edition'
    for i in range(2):
        ekey = mock_site.new_key(etype)
        e = {
            'title'        : 'test1',
            'type'         : {'key': etype},
            'lccn'         : ['123%d'%i],
            'oclc_numbers' : ['456%d'%i],
            'key'          : ekey,
            'ocaid'        : "12345%d"%i,
            'isbn_10'      : ["123456789%d"%i],
            'isbn_13'      : ["987123456789%d"%i],
            "works"        : [{ "key": wkey }]
            }
        mock_site.save(e)
        editions.append(ekey)
    
    ## Now create a work without any edition
    wkey = mock_site.new_key(wtype)
    w = {
        'title'        : 'editionless',
        'type'         : {'key': wtype},
        'key'          : wkey,
        }
    mock_site.save(w)    

    best_match = mock_site.get(editions[0]) # First one is the best match. The function should denormalise this
    search_results = editions + [wkey] # This will be the input to massage_search_results
    massaged_results = massage_search_results(search_results)
    
    # Check the fields in the main best match.
    for i in "key title".split(): # TODO: Check for the rest of the fields here
        assert massaged_results['doc'][i] == best_match[i], "Mismatch in %s field of massaged results and best match"%i
    assert massaged_results['doc']['isbn_10'] == best_match['isbn_10'], "Mismatch in ISBN10 field of massaged results and best match"
    assert massaged_results['doc']['isbn_13'] == best_match['isbn_13'], "Mismatch in ISBN13 field of massaged results and best match"

    # Check the fields in the remaining matches.
    # The first two matches should be the editions and then the work match (the order of the input)
    expected_matches = [ {'edition' : editions[0], 'work' : mock_site.get(editions[0]).works[0].key},
                         {'edition' : editions[1], 'work' : mock_site.get(editions[1]).works[0].key},
                         {'edition' : None, 'work' : wkey } ]

    assert massaged_results['matches'] == expected_matches, "Matches field got a different value"


def test_create_edition(mock_site):
    "Creation of editions"
    record = {'doc': {'isbn_10': ['1234567890'],
                      'key': None,
                      'publish_date': '2012',
                      'publishers': 'Dover',
                      'title': 'THIS IS A TEST BOOK',
                      'type': {'key': '/type/edition'},
                      'works': [{'key': None,
                                 'title': 'This is a test book',
                                 'type': {'key': '/type/work'},
                                 'authors': [{'author': {'birth_date': '1979',
                                                         'death_date': '2010',
                                                         'key': None,
                                                         'name': 'Test Author 1'}},
                                             {'author': {'birth_date': '1979',
                                                         'death_date': '2010',
                                                         'key': None,
                                                         'name': 'Test Author 2'}}]
                    }]}}
    
    r = create(record)
    new_edition = mock_site.get(r)
    new_work = mock_site.get(new_edition.works[0]['key'])
    new_authors = [mock_site.get(x.author) for x in new_work.authors]
    assert new_edition.title == "THIS IS A TEST BOOK"
    assert new_work.title == 'This is a test book'
    assert new_authors[0].name == 'Test Author 1' and new_authors[1].name == 'Test Author 2'

def test_update_edition(mock_site):
    "Update edition records in the database."
    # First create a record using our existing API
    record = {'doc': {'isbn_10': ['1234567890'],
                      'key': None,
                      'title': 'THIS IS A TEST BOOK',
                      'type': {'key': '/type/edition'},
                      'works': [{'key': None,
                                 'title': 'This is a test book',
                                 'type': {'key': '/type/work'},
                                 'authors': [{'author': {'birth_date': '1979',
                                                         'death_date': '2010',
                                                         'key': None,
                                                         'name': 'Test Author 1'}},
                                             {'author': {'birth_date': '1979',
                                                         'death_date': '2010',
                                                         'key': None,
                                                         'name': 'Test Author 2'}}]
                    }]}}
    
    edition_key = create(record)
    new_edition = mock_site.get(edition_key)
    new_work_key = new_edition.works[0]['key']
    new_work = mock_site.get(new_work_key)
    new_author0, new_author1 = [mock_site.get(x.author) for x in new_work.authors]

    ## Edition update
    # First try adding a publisher and date to the edition
    record = {'doc': {'isbn_10': ['1234567890'],
                      'key': edition_key,
                      'publish_date': '2012',
                      'publishers': 'Dover',
                      'title': 'THIS IS A TEST BOOK',
                      'type': {'key': '/type/edition'}
                      }}
    updated_edition_key = create(record)
    updated_work_key = new_edition.works[0]['key']
    updated_author_key0, updated_author_key1 = [x.author for x in mock_site.get(updated_work_key).authors]

    # Make sure that old things are as they were
    assert updated_edition_key == edition_key, "Change in edition key after updating. Updated : %s, Original : %s"%(updated_edition_key, edition_key)
    assert updated_work_key == new_work.key, "Change in work key after updating"
    assert updated_author_key0 == new_author0.key and updated_author_key1 == new_author1.key, "Change in author keys after updating"

    # Now check for the new fields
    updated_edition = mock_site.get(edition_key) # Get the original one. 
    assert updated_edition.publishers == "Dover"
    assert updated_edition.publish_date == "2012"
    
def test_update_work(mock_site):
    "Update work records in the database"
    # First create a record using our existing API
    record = {'doc': {'isbn_10': ['1234567890'],
                      'key': None,
                      'title': 'THIS IS A TEST BOOK',
                      'type': {'key': '/type/edition'},
                      'works': [{'key': None,
                                 'title': 'This is a test book',
                                 'type': {'key': '/type/work'},
                                 'authors': [{'author': {'birth_date': '1979',
                                                         'death_date': '2010',
                                                         'key': None,
                                                         'name': 'Test Author 1'}},
                                             {'author': {'birth_date': '1979',
                                                         'death_date': '2010',
                                                         'key': None,
                                                         'name': 'Test Author 2'}}]
                    }]}}
    
    edition_key = create(record)
    new_edition = mock_site.get(edition_key)
    new_work_key = new_edition.works[0]['key']
    new_work = mock_site.get(new_work_key)
    new_author0, new_author1 = [mock_site.get(x.author) for x in new_work.authors]

    ## Work update
    record = {'doc': {'key': new_work_key,
                      'title': 'This is a new test book', #Changed the title here. 
                      'type': {'key': '/type/work'},
                      }}
    
    r = create(record)
    assert new_work_key == r, "Work key has changed (Original : %s, New : %s)"%(new_work_key, r)
    updated_work = mock_site.get(r)
    assert updated_work.title == "This is a new test book", "Work title has not changed"
    
    ## TODO : Adding, updating authors and other list items.
    

def test_find_matches_by_identifiers(mock_site):
    "Validates the all and any return values of find_matches_by_identifiers"
    # First create 2 records
    record0 = {'doc': {'isbn_10': ['1234567890'],
                      'identifiers' : {"oclc_numbers" : ["1807182"],
                                       "lccn": [ "34029558"]},
                      'key': None,
                      'title': 'THIS IS A TEST BOOK',
                      'type': {'key': '/type/edition'}}}

    record1 = {'doc': {'isbn_10': ['09876543210'],
                          'identifiers' : {"oclc_numbers" : ["2817081"],
                                           "lccn": [ "34029558"]},
                          'key': None,
                          'title': 'THIS IS A TEST BOOK',
                          'type': {'key': '/type/edition'}}}
    
    edition_key0 = create(record0)    
    edition_key1 = create(record1)

    q = {'identifiers' : {'oclc_numbers': "1807182",
                          'lccn': '34029558'}}
                              
    results = find_matches_by_identifiers(q)

    assert results["all"] == [edition_key0]
    assert results["any"] == [edition_key0, edition_key1]
    
    

    
    
    
def test_search_isbn(mock_site):
    "Try to search for a record which should match by ISBN"
    # First create a record using our existing API

    record = {'doc': {'isbn_10': ['1234567890'],
                      'key': None,
                      'title': 'THIS IS A TEST BOOK',
                      'type': {'key': '/type/edition'},
                      'works': [{'key': None,
                                 'title': 'This is a test book',
                                 'type': {'key': '/type/work'},
                                 'authors': [{'author': {'birth_date': '1979',
                                                         'death_date': '2010',
                                                         'key': None,
                                                         'name': 'Test Author 1'}},
                                             {'author': {'birth_date': '1979',
                                                         'death_date': '2010',
                                                         'key': None,
                                                         'name': 'Test Author 2'}}]
                                 }]}}
    
    edition_key = create(record)
    
    search_input = {'doc' : {'identifiers' : {'isbn' : [1234567890]}}}
    search_results = search(search_input)
    best = search_results.pop("doc")
    rest = search_results.pop("matches")
    assert best['key'] == edition_key, "Best didn't match by ISBN"
    assert rest[0]['edition'] == edition_key, "Edition mismatch in matches %s and %s"%(rest[0]['edition'], edition_key)
    assert rest[0]['work'] == best['works'][0]['key'], "Work mismatch in matches %s and %s"%(rest[0]['work'], best['works'][0]['key'])
    
    
    

