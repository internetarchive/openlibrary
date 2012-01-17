"""
Functions which are used by the records package. The two public ones
are `search` and `create` which are callable from the outside world.
"""

def search(params):
    """
    Takes a search parameter and returns a result set

    Input:
    ------

    {'doc': {'identifiers': {'goodreads': ['12345', '12345'],
                             'isbn': ['1234567890'],
                             'lcc': ['123432'],
                             'librarything': ['12312', '231123']},
             'publish_year': '1995',
             'publisher': 'Bantam',
             'title': 'A study in Scarlet'}}

    Output:
    -------

    {'doc': {'isbn': ['1234567890'],
             'key': '/books/OL1M',
             'publish_year': '1995',
             'publisher': 'Bantam',
             'title': 'A study in Scarlet',
             'type': {'key': '/type/edition'},
             'work': [{'authors': [{'authors': [{'birth_date': '1859',
                                                 'death_date': '1930',
                                                 'key': '/author/OL1A',
                                                 'name': 'Arthur Conan Doyle'}]}],
                       'key': '/works/OL1M',
                       'title': 'A study in scarlet',
                       'type': {'key': '/type/work'}}]},
     'matches': [{'edition': '/books/OL1M', 'work': '/works/OL1W'},
                 {'edition': None, 'work': '/works/OL234W'}]}

    'doc' is the best fit match. It's denormalised for convenience. 
    'matches' is a list of possible matches. 

    If a match couldn't be found for a record (e.g. edition), the
    corresponding key will be None.

    """
    doc = params.pop("doc")
    # {'doc': {'identifiers': {'goodreads': ['12345', '12345'],
    #                          'isbn': ['1234567890'],
    #                          'lcc': ['123432'],
    #                          'librarything': ['12312', '231123']},
    #          'publish_year': '1995',
    #          'publisher': 'Bantam',
    #          'title': 'A study in Scarlet'}}

    # Step 1: Search for the results.
    # If we have ISBNS, search using that.

    # Step 2: Pick the best one and expand it.

    # Step 3: Construct the response and return it. 
    
    
        

def create(records):
    """
    """
    pass
