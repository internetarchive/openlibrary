#!/usr/bin/python

import unittest
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
]

class TestNames(unittest.TestCase):
    def setUp(self):
        names.verbose = True
    def testnames(self):
        for amazon, marc in samples:
            self.assert_(names.match_name(amazon, marc))

if __name__ == '__main__':
    unittest.main()
