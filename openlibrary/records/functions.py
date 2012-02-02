"""
Functions which are used by the records package. The two public ones
are `search` and `create` which are callable from the outside world.
"""

import copy

import web

from openlibrary.catalog.add_book import normalize
import openlibrary.core.helpers as h

class NoQueryParam(KeyError):
    """
    Exception that is used internally when a find_by_X function is
    called but no X parameters were provided.
    """
    pass
    


def search(params):
    """
    Takes a search parameter and returns a result set

    Input:
    ------
    {'doc': {'authors': [{'name': 'Arthur Conan Doyle'}],
             'identifiers': {'isbn': ['1234567890']},
             'title': 'A study in Scarlet'}}

    Output:
    -------
    {'doc': {'authors': [
                         {
                          'key': '/authors/OL1A', 
                          'name': 'Arthur Conan Doyle'
                         }
                        ],
             'identifiers': {'isbn': ['1234567890']},
             'key': '/books/OL1M',
             'title': 'A study in Scarlet'
             'work' : { 'key' : '/works/OL1W'}
             },

     'matches': [{'edition': '/books/OL1M', 'work': '/works/OL1W'},
                 {'edition': None, 'work': '/works/OL234W'}]}

    'doc' is the best fit match. It contains only the keys that were
    provided as input and one extra key called 'key' which will be
    openlibrary identifier if one was found or None if nothing was.

    There will be two extra keys added to the 'doc'. 

     1. 'work' which is a dictionary with a single element 'key' that
        contains a link to the work of the matched edition.
     2. 'authors' is a list of dictionaries each of which contains an
        element 'key' that links to the appropriate author.

     If a work, author or an edition is not matched, the 'key' at that
     level will be None. 

     To update fields in a record, add the extra keys to the 'doc' and
     send the resulting structure to 'create'.

     'matches' contain a list of possible matches ordered in
     decreasing order of certainty. The first one will be same as
     'doc' itself.

     TODO: Things to change

     1. For now, if there is a work match, the provided authors
        will be replaced with the ones that are stored.

    """
    params = copy.deepcopy(params)
    doc = params.pop("doc")
    
    matches = []
    # TODO: We are looking only at edition searches here. This should be expanded to works.  
    if "isbn" in doc.get('identifiers',{}):
        matches.extend(find_matches_by_isbn(doc['identifiers']['isbn']))

    if "identifiers" in doc:
        d = find_matches_by_identifiers(doc['identifiers'])
        matches.extend(d['all'])
        matches.extend(d['any']) # TODO: These are very poor matches. Maybe we should put them later.

    if "publisher" in doc or "publish_year" in doc or "title" in doc:
        matches.extend(find_matches_by_title_and_publishers(doc))

    print "Narrowing to %s"%doc.keys()
    return massage_search_results(matches, doc.keys())



def find_matches_by_isbn(isbns):
    "Find matches using isbns."
    q = {
        'type':'/type/edition',
        'isbn_': str(isbns[0])
        }
    ekeys = list(web.ctx.site.things(q))
    if ekeys:
        return ekeys[:1] # TODO: We artificially match only one item here
    else:
        return []


def find_matches_by_identifiers(identifiers):
    """Find matches using all the identifiers in the given doc.

    We consider only oclc_numbers, lccn and ocaid. isbn is dealt with
    separately.
    
    Will return two lists of matches: 
      all : List of items that match all the given identifiers (better
            matches).
      any : List of items that match any of the given identifiers
            (poorer matches).

    """

    identifiers = copy.deepcopy(identifiers)
    # Find matches that match everything.
    q = {'type':'/type/edition'}
    for i in ["oclc_numbers", "lccn", "ocaid"]:
        if i in identifiers:
            q[i] = identifiers[i]
    matches_all = web.ctx.site.things(q)

    # Find matches for any of the given parameters and take the union
    # of all such matches
    matches_any = set()
    for i in ["oclc_numbers", "lccn", "ocaid"]:
        q = {'type':'/type/edition'}
        if i in identifiers:
            q[i] = identifiers[i]
            matches_any.update(web.ctx.site.things(q))
    matches_any = list(matches_any)
    return dict(all = matches_all, any = matches_any)

def find_matches_by_title_and_publishers(doc):
    "Find matches using title and author in the given doc"
    #TODO: Use normalised_title instead of the regular title
    #TODO: Use catalog.add_book.load_book:build_query instead of this
    q = {'type'  :'/type/edition'}
    for key in ["title", 'publishers', 'publish_year']:
        if key in doc:
            q[key] = doc[key]
    ekeys = web.ctx.site.things(q)
    return ekeys

def massage_search_results(keys, limit_keys = []):
    """Converts list of keys into the output expected by users of the search API.

    If limit_keys is non empty, remove keys other that these in the 'doc' section.
    """
    best = keys[0]
    # TODO: Inconsistency here (thing for to_doc and keys for to_matches)
    doc = thing_to_doc(web.ctx.site.get(best), limit_keys)
    matches = things_to_matches(keys)
    return {'doc' : doc,
            'matches' : matches}
    

def edition_to_doc(thing):
    """Converts an edition document from infobase into a 'doc' used by
    the search API.
    """
    doc = thing.dict()

    # Process identifiers
    identifiers = doc.get("identifiers",{})
    for i in ["oclc_numbers", "lccn", "ocaid"]:
        if i in doc:
            identifiers[i] = doc.pop(i)
    for i in ["isbn_10", "isbn_13"]:
        if i in doc:
            identifiers.setdefault('isbn',[]).extend(doc.pop(i)) 
    doc['identifiers'] = identifiers

    # TODO : Process classifiers here too

    # Unpack works and authors
    work = doc.pop("works")[0]
    doc['work'] = work
    authors = [{'key': str(x.author) } for x in thing.works[0].authors]
    doc['authors'] = authors

    return doc
    

def work_to_doc(thing):
    """
    Converts the given work into a 'doc' used by the search API.
    """
    doc = thing.dict()

    # Unpack works and authors
    authors = [{'key': x.author.key } for x in thing.authors]
    doc['authors'] = authors

    return doc

def author_to_doc(thing):
    return thing.dict()


def thing_to_doc(thing, keys = []):
    """Converts an infobase 'thing' into an entry that can be used in
    the 'doc' field of the search results.

    If keys provided, it will remove all keys in the item except the
    ones specified in the 'keys'.
    """
    typ = str(thing['type'])
    key = str(thing['key'])

    processors = {'/type/edition' : edition_to_doc,
                  '/type/work' : work_to_doc,
                  '/type/author' : author_to_doc}

    doc = processors[typ](thing)

    # Remove version info
    for i in ['latest_revision', 'last_modified', 'revision']:
        if i in doc:
            doc.pop(i)

    # Unpack 'type'
    doc['type'] = doc['type']['key']

    if keys:
        keys += ['key', 'type', 'authors', 'work']
        keys = set(keys)
        for i in doc.keys():
            if i not in keys:
                doc.pop(i)

    return doc

def things_to_matches(keys):
    """Converts a list of keys into a list of 'matches' used by the search API"""
    matches = []
    for i in keys:
        thing = web.ctx.site.get(i)
        if not thing:
            continue
        if i.startswith("/books"):
            edition = i
            work = thing.works[0].key
        if i.startswith("/works"):
            work = i
            edition = None
        matches.append(dict(edition = edition, work = work))
    return matches
            
            
            
        
        

# Creation/updation entry point
def create(records):
    """
    Creates one or more new records in the system.
    TODO: Describe Input/output
    """
    doc = records["doc"]
    things = doc_to_things(copy.deepcopy(doc))
    web.ctx.site.save_many(things, 'Import new records.')
    

# Creation helpers
def edition_doc_to_things(doc):
    """
    unpack identifers, classifiers

    Process work and author fields if present
    """
    retval = []
    # Unpack identifiers
    identifiers = doc.get("identifiers",{})
    for i in ["oclc_numbers", "isbn_10", "isbn_13", "lccn", "ocaid"]:
        if i in identifiers:
            doc[i] = identifiers.pop(i)
    # TODO: Unpack classifiers

    work = authors = None
    if 'work' in doc:
        work = doc.pop('work')
        work['type'] = '/type/work'
        work = doc_to_things(work)
        retval.extend(work)

    if 'authors' in doc:
        authors = doc.pop('authors')
        for i in authors:
            i['type'] = '/type/author'
        a = []
        for i in authors:
            a.extend(doc_to_things(i))
        retval.extend(a)
        authors = a

    # Attach authors to the work
    # TODO: Consider updation here?
    if work and authors:
        for i in authors:
            a = {'type': '/type/author_role', 'author': i['key']} #TODO : Check this with Anandb
            work[0].setdefault('authors',[]).append(a) # Attach this author to the work
    return retval


def work_doc_to_things(doc):
    new_things = []
    if 'authors' in doc:
        if all(isinstance(x, dict) for x in doc['authors']): # Ugly hack to prevent Things from being processed
            authors = doc['authors']
            author_entries = []
            for i in authors:
                i['type'] = '/type/author'
                new_author = doc_to_things(i)
                new_things.extend(new_author)
                a = {'type': '/type/author_role', 'author': new_author[0]['key']} #TODO : Check this with Anandb
                author_entries.append(a)
            doc['authors'] = author_entries
    return new_things


def author_doc_to_things(doc):
    return []

def doc_to_things(doc):
    """
    Receives a 'doc' (what the search API returns and receives) and
    returns a list of dictionaries that can be added into infobase.

    Expects the `type` to figure out type of object.

    Has separate sub functions to convert editions, works and
    authors. Logic is different for these three.

    This function will call itself for the 'work' and 'authors' fields
    if present.

    If the doc has a 'key', the thing corresponding to that key will
    be fetched from the database and the fields of the original doc
    updated.

    If the doc doesn't have a key, the function will call
    web.ctx.site.new_key, generate one for it and add that as the key.
    """
    retval = []
    doc = copy.deepcopy(doc)
    key = doc.get('key')
    typ = doc['type']
    # Handle key creation and updation of data
    if key:
        db_thing = web.ctx.site.get(key)
        for i in db_thing:
            if i in doc:
                db_thing.pop(i)
        doc.update(db_thing)
    else:
        key = web.ctx.site.new_key(typ)
        doc['key'] = key
    
    # Type specific processors
    processors = {'/type/edition' : edition_doc_to_things,
                  '/type/work'    : work_doc_to_things,
                  '/type/author'  : author_doc_to_things}
    extras = processors[typ](doc)
    retval.append(doc)
    retval.extend(extras)

    return retval

    
    




#################################### OLD STUFF ########################################3    
# def search(params):
#     """
#     Takes a search parameter and returns a result set

#     Input:
#     ------

#     {'doc': {'identifiers': {'goodreads': ['12345', '12345'],
#                              'isbn': ['1234567890'],
#                              'lcc': ['123432'],
#                              'librarything': ['12312', '231123']},
#              'publish_year': '1995',
#              'publishers': ['Bantam'],
#              'title': 'A study in Scarlet'
#              'authors': ["Arthur Conan Doyle", ...]}}

#     Output:
#     -------

#     {'doc': {'isbn': ['1234567890'],
#              'key': '/books/OL1M',
#              'publish_year': '1995',
#              'publishers': ['Bantam'],
#              'title': 'A study in Scarlet',
#              'type': {'key': '/type/edition'},
#              'work': [{'authors': [{'authors': [{'birth_date': '1859',
#                                                  'death_date': '1930',
#                                                  'key': '/author/OL1A',
#                                                  'name': 'Arthur Conan Doyle'}]}],
#                        'key': '/works/OL1M',
#                        'title': 'A study in scarlet',
#                        'type': {'key': '/type/work'}}]},
#      'matches': [{'edition': '/books/OL1M', 'work': '/works/OL1W'},
#                  {'edition': None, 'work': '/works/OL234W'}]}

#     'doc' is the best fit match. It's denormalised for convenience. 
#     'matches' is a list of possible matches. 

#     If a match couldn't be found for a record (e.g. edition), the
#     corresponding key will be None.

#     """
#     params = copy.deepcopy(params)
#     doc = params.pop("doc")
#     matches = []
#     # Step 1: Search for the results. 
#     # TODO: We are looking only at edition searches here. This should be expanded to works.

#     # 1.1 If we have ISBNS, search using that.
#     try:
#         matches.extend(find_matches_by_isbn(doc))
#     except NoQueryParam,e:
#         pass                                                                                 

#     # 1.2 If we have identifiers, search using that.
#     try:
#         d = find_matches_by_identifiers(doc)
#         matches.extend(d['all'])
#         matches.extend(d['any']) # TODO: These are very poor matches. Maybe we should put them later.
#     except NoQueryParam,e:
#         pass

#     # 1.3 Now search by title and publishers
#     try:
#         d = find_matches_by_title_and_publishers(doc)
#         matches.extend(d)
#     except NoQueryParam,e:
#         pass

#     # Step 2: Convert search results into API return format and return it
#     results = massage_search_results(matches)
#     return results


# def find_matches_by_title_and_publishers(doc):
#     "Find matches using title and author in the given doc"
#     try:
#         #TODO: Use normalised_title instead of the regular title
#         #TODO: Use catalog.add_book.load_book:build_query instead of this
#         q = {'type'  :'/type/edition'}
#         for key in ["title", 'publishers', 'publish_year']:
#             if key in doc:
#                 q[key] = doc[key]
#         ekeys = web.ctx.site.things(q)
#         return ekeys
#     except KeyError, e:
#         raise NoQueryParam(str(e))

# def find_matches_by_identifiers(doc):
#     """Find matches using all the identifiers in the given doc.

#     We consider only oclc_numbers, lccn and ocaid. isbn is dealt with
#     separately.
    
#     Will return two lists of matches: 
#       all : List of items that match all the given identifiers (better
#             matches).
#       any : List of items that match any of the given identifiers
#             (poorer matches).

#     """

#     try:
#         identifiers = copy.deepcopy(doc['identifiers'])
#         if "isbn" in identifiers: 
#             identifiers.pop("isbn")

#         # Find matches that match everything.
#         q = {'type':'/type/edition'}
#         for i in ["oclc_numbers", "lccn", "ocaid"]:
#             if i in identifiers:
#                 q[i] = identifiers[i]
#         matches_all = web.ctx.site.things(q)

#         # Find matches for any of the given parameters and take the union
#         # of all such matches
#         matches_any = set()
#         for i in ["oclc_numbers", "lccn", "ocaid"]:
#             q = {'type':'/type/edition'}
#             if i in identifiers:
#                 q[i] = identifiers[i]
#                 matches_any.update(web.ctx.site.things(q))
#         matches_any = list(matches_any)
#         return dict(all = matches_all, any = matches_any)
#     except KeyError, e:
#         raise NoQueryParam(str(e))
    
        

# def find_matches_by_isbn(doc):
#     "Find matches using isbns."
#     try:
#         isbns = doc['identifiers']["isbn"]
#         q = {
#             'type':'/type/edition',
#             'isbn_10': str(isbns[0]) #TODO: Change this to isbn_
#             }
#         ekeys = list(web.ctx.site.things(q))
#         if ekeys:
#             return ekeys[:1] # TODO: We artificially match only one item here
#         else:
#             return []
#     except KeyError, e:
#         raise NoQueryParam(str(e))

# def denormalise(item):
#     "Denormalises the given item as required by the search results. Used for the best match."
#     def expand_authors(authors):
#         expanded_authors = []
#         for a in authors:
#             expanded_authors.append(a.dict())
#         return expanded_authors

#     def expand_works(works):
#         expanded_works = []
#         for w in works:
#             d = w.dict()
#             authors = expand_authors(w.authors)
#             d['authors'] = authors
#             expanded_works.append(d)
#         return expanded_works

#     def expand_edition(edition):
#         "Expands an edition"
#         expanded_edition = edition.dict()
#         # First expand the identifiers
#         identifiers = {}
#         if "isbn_10" in edition and edition["isbn_10"]:
#             identifiers.setdefault('isbn',[]).extend(edition["isbn_10"])
#         if "isbn_13" in edition and edition["isbn_13"]:
#             identifiers.setdefault('isbn',[]).extend(edition["isbn_13"])
#         edition.identifiers.update(identifiers)
#         # Recursively expand the works
#         works = expand_works(edition.works)
#         # Fixup the return value and return it. 
#         expanded_edition['identifiers'] = identifiers
#         expanded_edition['works'] = works
#         return expanded_edition

#     thing = web.ctx.site.get(item)
#     if item.startswith("/books/"):
#         return expand_edition(thing)
#     elif item.startswith("/works/"):
#         return expand_works([thing])[0]
        
# def expand(item):
#     "Expands an edition or thing into a dictionary used for the search results"
#     thing = web.ctx.site.get(item)
#     if item.startswith("/books/"):
#         return {"edition" : item, "work" : thing.works and thing.works[0].key} #TODO: Is it right to simply use the first?
#     if item.startswith("/works/"):
#         return {"edition" : None, "work" : item} 

# def massage_search_results(matches):
#     "Converts a list of keys into the return format of the search API"
#     matches= h.uniq(matches)
#     first = matches[0]
#     all = matches
#     # Denormalise the best match
#     best_match = denormalise(first)
    
#     # Enumerage the rest of the matches
#     matches = []
#     for i in all:
#         matches.append(expand(i))

#     return {"doc" : best_match,
#             "matches" : matches}
    

