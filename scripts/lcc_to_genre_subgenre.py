#!/usr/bin/env python3

import json
import os
import string

# from typing import Tuple

here = os.path.dirname(os.path.abspath(__file__))

# Load two Python dicts with Library of Congress Classification conversion data
with open(os.path.join(here, "lc_classifiers_letters_only.json")) as in_file:
    lcc_letters_only = json.load(in_file)
with open(os.path.join(here, "lc_classifiers_letters_and_numbers.json")) as in_file:
    lcc_letters_and_numbers = json.load(in_file)
out_file = None


def parse_lcc(lcc):
    """
    def parse_lcc(lcc: str) -> Tuple[str, int]:

    >>> parse_lcc("HB1951 .R64 1995")
    ('HB', 1951)
    >>> parse_lcc("DP402.C8 O46 1995")
    ('DP', 402)
    >>> parse_lcc("CS879 .R3 1995")
    ('CS', 879)
    """
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


def lcc_to_genre_subgenre(lcc):
    """
    def lcc_to_genre_subgenre(lcc: str) -> list:
    """
    genre_subgenre = letters_only(lcc)
    if len(genre_subgenre) != 2:
        for subgenre in lcc_to_subject(lcc):
            if subgenre not in genre_subgenre:
                genre_subgenre.append(subgenre)
                if len(genre_subgenre) >= 2:
                    break
        print("Needed numbers:", lcc)
        if out_file:
            print("Needed numbers:", lcc, file=out_file)
    return genre_subgenre


if __name__ == "__main__":
    import doctest

    doctest.testmod()

    print("\nPlease enter Library of Congress codes like: HB1951 .R64 1995...")
    with open(__file__ + "_debug.txt", "a+") as out_file:
        while True:
            lcc = input("Or leave blank to quit: ").strip().upper()
            if not lcc:
                break
            genre_subgenre = lcc_to_genre_subgenre(lcc)
            print(lcc, genre_subgenre)
            if len(genre_subgenre) != 2:
                print(lcc, genre_subgenre, file=out_file)
