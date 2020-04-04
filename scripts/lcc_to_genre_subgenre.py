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
    if lcc.startswith("OL"):
        return parse_lcc(olid_to_lc_classifications(lcc)[0])
    lcc = lcc.replace(" ", "").replace(".", " ").replace("/", " ").split()[0].upper()
    chars = ""
    for i, char in enumerate(lcc):
        if char in string.ascii_uppercase:
            chars += char
        else:
            return chars, int(lcc[i:])
    return chars, 0


def letters_only(lcc):
    """
    def letters_only(lcc: str) -> list:

    >>> letters_only("ZA")  # doctest: +NORMALIZE_WHITESPACE
    ['Bibliography. Library Science. Information resources',
     'Information resources/materials']
    >>> letters_only("za")  # doctest: +NORMALIZE_WHITESPACE
    ['Bibliography. Library Science. Information resources',
     'Information resources/materials']
    """
    lcc, _ = parse_lcc(lcc)
    return [x for x in (lcc_letters_only[lcc[0]], lcc_letters_only.get(lcc)) if x]


def lcc_to_subject(lcc):
    """
    def lcc_to_subject(lcc: str) -> list:

    >>> lcc_to_subject("ZA3201")
    ['Information resources (General)', 'Information superhighway']
    >>> lcc_to_subject("za3201")
    ['Information resources (General)', 'Information superhighway']
    """
    chars, number = parse_lcc(lcc)
    data = lcc_letters_and_numbers.get(chars, [])
    return [item["subject"] for item in data if item["start"] <= number <= item["stop"]]


def lcc_to_class_subclass(lcc):
    """
    def lcc_to_class_subclass(lcc: str) -> list:
    """
    class_subclass = letters_only(lcc)
    if len(class_subclass) != 2:
        if len(lcc) > 2:  # Drop the last char and redo
            return lcc_to_class_subclass(lcc[:-1])
        print("Falling thru...", lcc)
        if out_file:
            print("Falling thru...", lcc, file=out_file)
        for subclass in lcc_to_subject(lcc):
            if subclass not in class_subclass:
                class_subclass.append(subclass)
                if len(class_subclass) >= 2:
                    break
        print("Needed numbers:", lcc)
        if out_file:
            print("Needed numbers:", lcc, file=out_file)
    return class_subclass


if __name__ == "__main__":
    import doctest

    doctest.testmod()

    print("\nPlease enter Library of Congress codes like: HB1951 .R64 1995...")
    with open(__file__ + "_debug.txt", "a+") as out_file:
        while True:
            lcc = input("Or leave blank to quit: ").strip().upper()
            if not lcc:
                break
            class_subclass = lcc_to_class_subclass(lcc)
            print(lcc, class_subclass)
            if len(class_subclass) != 2:
                print(lcc, class_subclass, file=out_file)
