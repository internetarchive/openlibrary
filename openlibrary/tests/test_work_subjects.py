import unittest
from openlibrary.solr.work_subject import four_types, find_subjects

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

        marc = [[
            ('650', ' 0\x1faRhodes, Dan (Fictitious character)\x1fvFiction.\x1e'),
            ('650', ' 0\x1faSheriffs\x1fvFiction.\x1e'),
            ('651', ' 0\x1faTexas\x1fvFiction.\x1e')
        ]]

        expect = {}

        self.assertEqual(find_subjects(marc), expect)
        

