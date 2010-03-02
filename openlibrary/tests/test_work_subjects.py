import unittest
from openlibrary.solr.work_subject import four_types

class TestWorkSubjects(unittest.TestCase):
    def testFourTypes(self):
        input = {
            'subject': { 'Science': 2 },
            'event': { 'Party': 1 },
        }
        expect = {
            'subject': { 'Science': 2, 'Party': 1 },
        }
        self.assertEqual(four_types(input), expect)

        input = {
            'event': { 'Party': 1 },
        }
        expect = {
            'subject': { 'Party': 1 },
        }
        self.assertEqual(four_types(input), expect)

