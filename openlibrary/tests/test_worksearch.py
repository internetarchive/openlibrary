import unittest
from openlibrary.plugins.worksearch.code import search, advanced_to_simple

class TestWorkSearch(unittest.TestCase):
    def setUp(self):
        self.search = search()
    def testRedirect(self):
        def clean(i):
            return self.search.clean_inputs(i)
        self.assertEqual(clean({}), None)
        self.assertEqual(clean({'title':''}), {'title': None})
        self.assertEqual(clean({'title':'Test ', 'subject': ' '}), {'title': 'Test', 'subject': None})

    def test_adv1(self):
        params = {
            'q': 'Test search',
            'title': 'Test title',
            'author': 'John Smith'
        }
        expect = 'Test search title:(Test title) author:(John Smith)'
        self.assertEqual(advanced_to_simple(params), expect)

    def test_adv2(self):
        params = { 'q': '*:*', 'title': 'Test title' }
        expect = 'title:(Test title)'
        self.assertEqual(advanced_to_simple(params), expect)


