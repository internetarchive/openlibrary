"""
OL Import API OPDS parser
"""

import import_edition_builder

def parse_title(e):
    return e.text

def parse_author(e):
    name = e.find('{http://www.w3.org/2005/Atom}name')    
    return name.text
    
parser_map = {
    '{http://www.w3.org/2005/Atom}title':  ['title',  parse_title],
    '{http://www.w3.org/2005/Atom}author': ['author', parse_author]
}

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