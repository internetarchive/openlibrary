#!/usr/bin/env python

"""
This example uses the import_edition_builder class to convert
an IA meta.xml into a json object that the Import API can consume.

usage:
> python metaxml_to_json.py romanceonthreele00hafnrich_meta.xml
{
    "publishers": ["New York : Bloomsbury"],
    "description": "Includes bibliographical references (p. [243]-247) and index",
    "title": "A romance on three legs : Glenn Gould's obsessive quest for the perfect piano",
    "isbn_10": ["1596915250"],
    "isbn_13": ["9781596915251"],
    "languages": ["eng"],
    "subjects": [
        "Lending library",
        "protected DAISY",
        "Accessible book",
        "Gould, Glenn, 1932-1982",
        "Steinway piano",
    ],
    "publish_date": "2009",
    "authors": [
        {
            "entity_type": "person",
            "name": "Hafner, Katie",
            "personal_name": "Hafner, Katie",
        }
    ],
    "ocaid": "romanceonthreele00hafnrich",
}
"""

import lxml.etree

from openlibrary.plugins.importapi.import_edition_builder import import_edition_builder


def parse_collection(collection):
    collection_dict = {
        'printdisabled': ['Protected DAISY', 'Accessible book'],
        'lendinglibrary': ['Lending library', 'Protected DAISY', 'Accessible book'],
        'inlibrary': ['In library'],
    }

    return collection_dict.get(collection, [])


def parse_isbn(isbn):
    if len(isbn) == 13:
        return ('isbn_13', [isbn])
    elif len(isbn) == 10:
        return ('isbn_10', [isbn])
    else:
        return ('isbn', [])


def metaxml_to_edition_dict(root):
    ia_to_ol_map = {
        'identifier': 'ocaid',
        'creator': 'author',
        'date': 'publish_date',
        'boxid': 'ia_box_id',
    }

    edition_builder = import_edition_builder()

    for element in root.iter():
        # print("got %s -> %s" % (element.tag, element.text))

        if element.tag == 'collection':
            key = 'subject'
            values = parse_collection(element.text)
        elif element.tag == 'isbn':
            key, values = parse_isbn(element.text)
        elif element.tag in ia_to_ol_map:
            key = ia_to_ol_map[element.tag]
            values = [element.text]
        else:
            key = element.tag
            values = [element.text]

        for value in values:
            if key.startswith('ia_'):
                edition_builder.add(key, value, restrict_keys=False)
            else:
                edition_builder.add(key, value)

    return edition_builder.get_dict()


if __name__ == '__main__':
    import sys

    from lxml import etree

    assert len(sys.argv) == 2

    tree = etree.parse(sys.argv[1], parser=lxml.etree.XMLParser(resolve_entities=False))
    root = tree.getroot()

    edition_dict = metaxml_to_edition_dict(root)

    import json

    json_str = json.dumps(edition_dict)
    print(json_str)
