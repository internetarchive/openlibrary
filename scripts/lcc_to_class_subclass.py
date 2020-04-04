#!/usr/bin/env python3

from __future__ import print_function

import json
import os
import string

import requests  # python3 -m pip install requests

# from typing import Tuple

here = os.path.dirname(os.path.abspath(__file__))

# Load two Python dicts with Library of Congress Classification conversion data
with open(os.path.join(here, "lc_classifiers_letters_only.json")) as in_file:
    lcc_letters_only = json.load(in_file)
with open(os.path.join(here, "lc_classifiers_letters_and_numbers.json")) as in_file:
    lcc_letters_and_numbers = json.load(in_file)
out_file = None


def get_ol_book_info(olid="OL26617202M"):
    """
    def get_ol_book_info(olid: str = "OL26617202M") -> str:

    >>> get_ol_book_info()  # doctest: +ELLIPSIS
    {'olid:OL26617202M': ...
    """
    url = "https://openlibrary.org/api/books?jscmd=details&format=json&bibkeys=olid:"
    return requests.get(url + olid).json()


def olid_to_lc_classifications(olid="OL1025841M"):
    """
    def olid_to_lc_classifications(olid: str = "OL1025841M") -> list:

    >>> olid_to_lc_classifications()
    ['HB1951 .R64 1995']
    """
    return get_ol_book_info(olid)["olid:" + olid]["details"]["lc_classifications"]


def parse_lcc(lcc):
    """
    def parse_lcc(lcc: str) -> Tuple[str, int]:

    >>> parse_lcc("HB1951 .R64 1995")
    ('HB', 1951)
    >>> parse_lcc("OL1025841M")
    ('HB', 1951)
    >>> parse_lcc("DP402.C8 O46 1995")
    ('DP', 402)
    >>> parse_lcc("CS879 .R3 1995")
    ('CS', 879)
    """
    lcc = lcc.strip().upper()
    if lcc.startswith("OL"):  # User entered an OL number so convert it to LCC
        return parse_lcc(olid_to_lc_classifications(lcc)[0])
    lcc = lcc.replace(" ", "").replace(".", " ").replace("/", " ").split()[0].upper()
    chars = ""
    for i, char in enumerate(lcc):
        if char in string.ascii_uppercase:
            chars += char
        else:
            return chars, int(lcc[i:])
    return chars, 0


def lcc_to_classification(lcc):
    """
    def lcc_to_classification(lcc: str) -> list:

    >>> lcc_to_classification("ZA3201")  # doctest: +NORMALIZE_WHITESPACE
    ['Bibliography. Library Science. Information resources',
     'Information resources (General)', 'Information superhighway']
    >>> lcc_to_classification("za3201")  # doctest: +NORMALIZE_WHITESPACE
    ['Bibliography. Library Science. Information resources',
     'Information resources (General)', 'Information superhighway']
    """
    chars, number = parse_lcc(lcc)
    classification = [lcc_letters_only[chars[0]]]  # General works, Philosophy, History
    data = lcc_letters_and_numbers.get(chars)  # get the subdict for main-dict[chars]
    for item in data:  # for all items in the subdict where the number is in the range
        if item["start"] <= number <= item["stop"]:  # and not item["parents"]
            # print(chars, number, item)
            classification.append(item["subject"])  # add a subject to classification
    return classification


if __name__ == "__main__":
    import doctest

    doctest.testmod()

    print("\nPlease enter Library of Congress codes like: HB1951 .R64 1995...")
    with open(__file__ + "_debug.txt", "a+") as out_file:
        while True:
            lcc = input("Or leave blank to quit: ").strip().upper()
            if not lcc:
                break
            class_subclass = lcc_to_classification(lcc)
            print(lcc, class_subclass)
            # if len(class_subclass) != 2:
            print(lcc, class_subclass, file=out_file)
