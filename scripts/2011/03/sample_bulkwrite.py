"""Sample script to update OL records in bulk.
"""

from openlibrary.api import OpenLibrary
import web
import sys

ol = OpenLibrary()

def read_mapping(filename, chunksize=1000):
    """Reads OLID, OCLC_NUMBER mapping from given file.

    Assumes that the file contains one OLID, OCLC_NUMBER per line, separated by tab.
    """
    for line in open(filename):
        olid, oclc = line.strip().split("\t")
        yield olid, oclc

def add_identifier(doc, id_name, id_value):
    if id_name in ["isbn_10", "isbn_13", "oclc_numbers", "lccn"]:
        ids = doc.setdefault(id_name, [])
    else:
        ids = doc.setdefault("identifiers", {}).setdefault(id_name, [])

    if id_value not in ids:
        ids.append(id_value)

def has_identifier(doc, id_name, id_value):
    if id_name in ["isbn_10", "isbn_13", "oclc_numbers", "lccn"]:
        return id_value in doc.get(id_name, [])
    else:
        return id_value in doc.get("identifiers", {}).get(id_name, [])

def get_docs(keys):
    # ol.get_many returns a dict, taking values() to get the list of docs
    return ol.get_many(keys).values() 

def add_oclc_ids(filename):
    """Adds OCLC Ids to OL records.
    """
    for mapping in web.group(read_mapping(filename), 1000):
        mapping = dict(mapping)

        docs = get_docs(mapping.keys())

        # ignore docs that already have the oclc_number that we are about to set
        docs = [doc for doc in doc if not has_identifier(doc, "oclc_numbers", mapping[doc['key']])

        for doc in docs:
            add_identifier(doc, "oclc_numbers", mapping[doc['key']])

        if docs:
            ol.save_many(docs, comment="Added OCLC numbers.")

def main():
    ol.login("bot-name", "password-here")
    add_oclc_ids(sys.argv[1])
