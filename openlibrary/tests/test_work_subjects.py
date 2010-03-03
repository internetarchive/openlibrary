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

        expect = {
            'place': {u'Texas': 1},
            'subject': {u'Dan Rhodes (Fictitious character)': 1, u'Sheriffs': 1, u'Sheriffs in fiction': 1, u'Texas in fiction': 1, u'Fiction': 3}
        }

        self.assertEqual(find_subjects(marc), expect)

        marc = [[
            ('650', ' 0\x1faSpies\x1fzFrance\x1fzParis\x1fvFiction.\x1e'),
            ('651', ' 0\x1faFrance\x1fxHistory\x1fyDirectory, 1795-1799\x1fvFiction.\x1e')
        ]]

        expect = {
            'subject': {u'History': 1, u'France in fiction': 1, u'Spies': 1, u'Spies in fiction': 1, u'Fiction': 2},
            'place': {u'Paris': 1, u'France': 2},
            'time': {u'Directory, 1795-1799': 1}
        }

        self.assertEqual(find_subjects(marc), expect)
        

