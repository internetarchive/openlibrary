#!/usr/bin/python
# coding: utf-8

# run using py.tests:
# py.test name_tests.py

import names

samples = [
    ("John Smith", "Smith, John"),
    ("Diane DiPrima", "Di Prima, Diane."),
    ("Buckley, William F.", "William F. Buckley Jr."),
    ("Duong Thu Huong", u"Dương, Thu Hương."),
#    ("Deanne Spears", "Milan Spears, Deanne."),
#    ("Victor Erofeyev", "Erofeev, V. V."),
#    ("Courcy Catherine De", "De Courcy, Catherine."),
#    ("Andy Mayer", "Mayer, Andrew"),
#    ("Neelam Saran Gour", "Gour, Neelum Saran"),
#    ("Bankim Chandra Chatterjee", "Chatterji, Bankim Chandra "),
#    ("Mrs. Humphrey Ward", "Ward, Humphry Mrs."),
#    ("William F. Buckley Jr.", "Buckley, William F."),
#    ("John of the Cross Saint", "Saint John of the Cross"),
#    ('Louis Philippe', 'Louis Philippe King of the French'),
#    ('Gregory of Tours', 'Gregory Saint, Bishop of Tours'),
#    ('Marjorie Allen', 'Allen, Marjory Gill Allen, Baroness'),
    ('Shewbridge                   Ea', 'Shewbridge, Edythe.'),
    ('Maitland-Jones               Jf', 'Maitland-Jones, J. F.'),
    ('Quine                        Wv', 'Quine, W. V.'),
    ('Auden                        Wh', 'Auden, W. H.'),
    ('Evans                        Cm', 'Evans, Charles M.'),
    ('Buckwalter                   L', 'Buckwalter, Len.'),
    ('Bozic                        Sm', 'Bozic, S. M.'),
    ('Lawrence                     Dh', 'Lawrence, D. H.'),
    ('De Grazia                    T', 'De Grazia'),
    ('Purcell                      R', 'Purcell, Rosamond Wolff.'),
    ('Warring                      Rh', 'Warring, R. H.'),
]

def test_names():
    for amazon, marc in samples:
        yield check, amazon, marc

def test_flip_name():
    assert names.flip_name("Smith, John") == "John Smith"
    assert names.flip_name("John Smith") == None

def test_compare_part():
    assert names.compare_part("J", "John")
    assert names.compare_part("John", "J")
    assert not names.compare_part("John", "Jack")
    assert names.compare_part("j", "John")
    assert not names.compare_part("X", "John")

def test_remove_trailing_dot():
#    print names.remove_trailing_dot("Jr.")
#    assert names.remove_trailing_dot("Jr.") == "Jr."
    assert names.remove_trailing_dot("John Smith.") == "John Smith"

def check(i, j):
    assert names.match_name(i, j)
