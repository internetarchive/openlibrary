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
# Make corrections...
# "D": "World History and History of Europe" -->
lcc_letters_only["D"] = "World History and History of Europe, Asia, Africa, Australia, New Zealand, Etc."
out_file = None


def get_ol_book_info(olid="OL26617202M"):
    """
    def get_ol_book_info(olid: str = "OL26617202M") -> str:
    >>> get_ol_book_info()  # doctest: +ELLIPSIS
    {'olid:OL26617202M': ...
    """
    params = {
        "bibkeys": "olid:" + olid,
        "format": "json",
        "jscmd": "details",
    }
    return requests.get("https://openlibrary.org/api/books", params=params).json()


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
    >>> parse_lcc("PR2782 H3 H4")
    ('PR', 2782)
    >>> parse_lcc("OL24614660M")
    ('PR', 2782)
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


def get_lcc_classes(lcc):
    """
    def get_lcc_classes(lcc: str) -> list:
    >>> get_lcc_classes("ZA3201")  # doctest: +NORMALIZE_WHITESPACE
    ['Bibliography. Library Science. Information resources',
     'Information resources (General)', 'Information superhighway']
    >>> get_lcc_classes("za3201")  # doctest: +NORMALIZE_WHITESPACE
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


lcc_to_classification = get_lcc_classes  # TODO: backward compatibility -- remove


def find_classification_strings(lcc="", strings=None):
    test_cases = {
        "DP402.C8 O46 1995": [
            "World History and History of Europe Asia, Africa, Australia, New Zealand, Etc.",
            "History of Spain",
            "Local history and description",
            "Other cities, towns, etc., A-Z",
        ],
    }
    if lcc and strings:
        chars, number = parse_lcc(lcc)
        try:
            assert strings[0] == lcc_letters_only[chars[0]], (
                f"First letter is wrong {lcc}: {strings[0]} == {lcc_letters_only[chars[0]]}")
        except AssertionError as e:
            print(e)
        found = get_lcc_classes(lcc)
        for i, s in enumerate(strings):
            if s in found:
                continue
            print(i, s)
            for key, value in lcc_letters_and_numbers.items():
                got_one = "\n".join(f"  {key}: {item}" for item in value if s in item["subject"])
                if got_one:
                    print(got_one)
    else:
        for key, value in test_cases.items():
            find_classification_strings(key, value)


if __name__ == "__main__":
    import doctest

    doctest.testmod()

    print("\nPlease enter Library of Congress codes like: HB1951 .R64 1995...")
    with open(__file__ + "_debug.txt", "a+") as out_file:
        while True:
            lcc = input("Or leave blank to quit: ").strip().upper()
            if not lcc:
                break
            class_subclass = get_lcc_classes(lcc)
            print(lcc, class_subclass)
            # if len(class_subclass) != 2:
            print(lcc, class_subclass, file=out_file)
