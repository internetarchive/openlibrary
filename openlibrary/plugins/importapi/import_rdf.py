"""
OL Import API RDF parser
"""

from openlibrary.plugins.importapi import import_edition_builder


def parse_string(e, key):
    return (key, e.text)


def parse_authors(e, key):
    authors = []
    for name in e.iterfind('.//{http://www.w3.org/1999/02/22-rdf-syntax-ns#}value'):
        authors.append(name.text)
    return (key, authors)


# Note that RDF can have subject elements in both dc and dcterms namespaces
# dc:subject is simply parsed by parse_string()
def parse_subject(e, key):
    member_of = e.find('.//{http://purl.org/dc/dcam/}memberOf')
    resource_type = member_of.get(
        '{http://www.w3.org/1999/02/22-rdf-syntax-ns#}resource'
    )
    val = e.find('.//{http://www.w3.org/1999/02/22-rdf-syntax-ns#}value')
    if 'http://purl.org/dc/terms/DDC' == resource_type:
        new_key = 'dewey_decimal_class'
        return (new_key, val.text)
    elif 'http://purl.org/dc/terms/LCC' == resource_type:
        new_key = 'lc_classification'
        return (new_key, val.text)
    else:
        return (None, None)


def parse_category(e, key):
    return (key, e.get('label'))


def parse_identifier(e, key):
    val = e.text
    isbn_str = 'urn:ISBN:'
    ia_str = 'http://www.archive.org/details/'
    if val.startswith(isbn_str):
        isbn = val[len(isbn_str) :]
        if 10 == len(isbn):
            return ('isbn_10', isbn)
        elif 13 == len(isbn):
            return ('isbn_13', isbn)
    elif val.startswith(ia_str):
        return ('ocaid', val[len(ia_str) :])
    else:
        return (None, None)


parser_map = {
    '{http://purl.org/ontology/bibo/}authorList': ['author', parse_authors],
    '{http://purl.org/dc/terms/}title': ['title', parse_string],
    '{http://purl.org/dc/terms/}publisher': ['publisher', parse_string],
    '{http://purl.org/dc/terms/}issued': ['publish_date', parse_string],
    '{http://purl.org/dc/terms/}extent': ['pagination', parse_string],
    '{http://purl.org/dc/elements/1.1/}subject': ['subject', parse_string],
    '{http://purl.org/dc/terms/}subject': ['subject', parse_subject],
    '{http://purl.org/dc/terms/}language': ['language', parse_string],
    '{http://purl.org/ontology/bibo/}lccn': ['lccn', parse_string],
    '{http://purl.org/ontology/bibo/}oclcnum': ['oclc_number', parse_string],
    '{http://RDVocab.info/elements/}placeOfPublication': [
        'publish_place',
        parse_string,
    ],
}
# TODO: {http://purl.org/dc/terms/}identifier (could be ocaid)
# TODO: {http://www.w3.org/2005/Atom}link     (could be cover image)


def parse(root):
    edition_builder = import_edition_builder.import_edition_builder()

    for e in root.iter():
        if isinstance(e.tag, str):
            # print e.tag
            if e.tag in parser_map:
                key = parser_map[e.tag][0]
                (new_key, val) = parser_map[e.tag][1](e, key)
                if new_key:
                    if isinstance(val, list):
                        for v in val:
                            edition_builder.add(new_key, v)
                    else:
                        edition_builder.add(new_key, val)
    return edition_builder
