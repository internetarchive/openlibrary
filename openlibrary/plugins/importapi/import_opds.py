"""
OL Import API OPDS parser
"""

import import_edition_builder

def parse_string(e, key):
    return (key, e.text)

def parse_author(e, key):
    name = e.find('{http://www.w3.org/2005/Atom}name')    
    return (key, name.text)

def parse_category(e, key):
    return (key, e.get('label'))

def parse_identifier(e, key):
    val = e.text
    isbn_str = 'urn:ISBN:'
    ia_str   = 'http://www.archive.org/details/'
    if val.startswith(isbn_str):
        isbn = val[len(isbn_str):]
        if 10 == len(isbn):
            return ('isbn_10', isbn)
        elif 13 == len(isbn):
            return ('isbn_13', isbn)
    elif val.startswith(ia_str):
        return ( 'ocaid', val[len(ia_str):] )
    else:
        return (None, None)

parser_map = {
    '{http://www.w3.org/2005/Atom}title':      ['title',         parse_string],
    '{http://www.w3.org/2005/Atom}author':     ['author',        parse_author],
    '{http://purl.org/dc/terms/}publisher':    ['publisher',     parse_string],
    '{http://purl.org/dc/terms/}issued':       ['publish_date',  parse_string],
    '{http://purl.org/dc/terms/}extent':       ['pagination',    parse_string],
    '{http://www.w3.org/2005/Atom}category':   ['subject',       parse_category],
    '{http://purl.org/dc/terms/}language':     ['language',      parse_string],
    '{http://www.w3.org/2005/Atom}summary':    ['description',   parse_string],
    '{http://purl.org/ontology/bibo/}lccn':    ['lccn',          parse_string],
    '{http://purl.org/ontology/bibo/}oclcnum': ['oclc_number',   parse_string],
    '{http://purl.org/dc/terms/}identifier':   ['identifier',    parse_identifier],
    '{http://RDVocab.info/elements/}placeOfPublication': ['publish_place', parse_string],    
}
#TODO: {http://purl.org/dc/terms/}identifier (could be ocaid)
#TODO: {http://www.w3.org/2005/Atom}link     (could be cover image)

def parse(root):
    edition_builder = import_edition_builder.import_edition_builder()
    
    for e in root:
        if isinstance(e.tag, basestring): 
            print e.tag
            if e.tag in parser_map:
                key = parser_map[e.tag][0]
                (new_key, val) = parser_map[e.tag][1](e, key)
                if new_key:
                    edition_builder.add(new_key, val)

    return edition_builder
