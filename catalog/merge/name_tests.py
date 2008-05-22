#!/usr/bin/python

# run using py.tests:
# py.test name_tests.py

import names

samples = [
    ("John Smith", "Smith, John"),
    ("Diane DiPrima", "Di Prima, Diane."),
    ("Deanne Spears", "Milan Spears, Deanne."),
    ("Victor Erofeyev", "Erofeev, V. V."),
    ("Courcy Catherine De", "De Courcy, Catherine."),
    ("Andy Mayer", "Mayer, Andrew"),
    ("Gour, Neelum Saran", "Neelam Saran Gour"),
    ("Bankim Chandra Chatterjee", "Chatterji, Bankim Chandra "),
    ("Mrs. Humphrey Ward", "Ward, Humphry Mrs."),
    ("William F. Buckley Jr.", "Buckley, William F."),
    ("John of the Cross Saint", "Saint John of the Cross"),
    ('Louis Philippe', 'Louis Philippe King of the French'),
    ('Gregory of Tours', 'Gregory Saint, Bishop of Tours'),
    ('Marjorie Allen', 'Allen, Marjory Gill Allen, Baroness'),
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

def check(i, j):
    assert names.match_name(i, j)
