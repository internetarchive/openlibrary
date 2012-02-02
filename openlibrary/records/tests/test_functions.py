import pytest


from ..functions import doc_to_things, create


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

def test_doc_to_thing_unpack_work_and_authors(mock_site):
    "Tests if the 'work' and 'author' fields in a doc are unpacked and converted."
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


    

    



    




    
    
