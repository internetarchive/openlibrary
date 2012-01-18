"""
Tests for the records package.
"""

from ..functions import search, create, massage_search_results


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
    
    for i in "key title".split(): # TODO: Check for the rest of the fields here
        assert massaged_results['doc'][i] == best_match[i], "Mismatch in %s field of massaged results and best match"%i
    assert massaged_results['doc']['isbn_10'] == best_match['isbn_10'], "Mismatch in ISBN10 field of massaged results and best match"

    # The first two matches should be the editions and then the work match (the order of the input)
    expected_matches = [ {'edition' : editions[0], 'work' : mock_site.get(editions[0]).works[0].key},
                         {'edition' : editions[1], 'work' : mock_site.get(editions[1]).works[0].key},
                         {'edition' : None, 'work' : wkey } ]

    assert massaged_results['matches'] == expected_matches, "Matches field got a different value"


