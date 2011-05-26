"""
OL Import API OPDS parser
"""

import import_edition_builder

def parse_string(e):
    return e.text

def parse_author(e):
    name = e.find('{http://www.w3.org/2005/Atom}name')    
    return name.text

def parse_category(e):
    return e.get('label')
    
parser_map = {
    '{http://www.w3.org/2005/Atom}title':    ['title',         parse_string],
    '{http://www.w3.org/2005/Atom}author':   ['author',        parse_author],
    '{http://purl.org/dc/terms/}publisher':  ['publisher',     parse_string],
    '{http://RDVocab.info/elements/}':       ['publish_place', parse_string],
    '{http://purl.org/dc/terms/}issued':     ['publish_date',  parse_string],
    '{http://purl.org/dc/terms/}extent':     ['pagination',    parse_string],
    '{http://www.w3.org/2005/Atom}category': ['subject',       parse_category],
    '{http://purl.org/dc/terms/}language':   ['language',      parse_string],
    '{http://purl.org/ontology/bibo/}lccn':  ['lccn',          parse_string],
}
#TODO: {http://purl.org/dc/terms/}identifier (could be ocaid)
#TODO: {http://www.w3.org/2005/Atom}link     (could be cover image)

def parse(element):
    edition_dict = import_edition_builder.import_edition_builder()
    
    for e in element.iter():
        if isinstance(e.tag, basestring):    
            print e.tag,
            print ' - '
            
            if e.tag in parser_map:
                key = parser_map[e.tag][0]
                val = parser_map[e.tag][1](e)
                edition_dict.add(key, val)
            print ' - '
            
        if isinstance(e.tag, basestring):
            if e.text:
                print e.tag,
                print ' - '
                #print e.text
            else:
                print e.tag
                #if e != element:
                #    parse(e)

    print 'made this dict'
    print edition_dict.get_dict()