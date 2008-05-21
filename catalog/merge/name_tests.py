#!/usr/bin/python

import unittest
import names

class TestNames(unittest.TestCase):
    def setUp(self):
        names.verbose = True
    def testnames(self):
        self.assert_(names.match_name("John Smith", "Smith, John"))
        self.assert_(names.match_name("Diane DiPrima", "Di Prima, Diane."))
        self.assert_(names.match_name("Deanne Spears", "Milan Spears, Deanne."))

if __name__ == '__main__':
    unittest.main()
