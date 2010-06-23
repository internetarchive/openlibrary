import unittest
from openlibrary.plugins.worksearch.code import search, advanced_to_simple, read_facets, sorted_work_editions, parse_query_fields, escape_bracket
from lxml.etree import fromstring

class TestWorkSearch(unittest.TestCase):
    def setUp(self):
        self.search = search()
    def test_escape_bracket(self):
        self.assertEqual(escape_bracket('foo'), 'foo')
        self.assertEqual(escape_bracket('foo['), 'foo\\[')
        self.assertEqual(escape_bracket('[ 10 TO 1000]'), '[ 10 TO 1000]')

#    the test is broken because the code was refactored
#    def testRedirect(self):
#        def clean(i):
#            return self.search.redirect_if_needed(i)
#        self.assertEqual(clean({}), None)
#        self.assertEqual(clean({'title':''}), {'title': None})
#        self.assertEqual(clean({'title':'Test ', 'subject': ' '}), {'title': 'Test', 'subject': None})

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

    def test_read_facet(self):
        xml = '''<response>
            <lst name="facet_counts">
                <lst name="facet_fields">
                    <lst name="has_fulltext">
                        <int name="false">46</int>
                        <int name="true">2</int>
                    </lst>
                </lst>
            </lst>
        </response>'''

        expect = {'has_fulltext': [('true', 'yes', '2'), ('false', 'no', '46')]}
        self.assertEqual(read_facets(fromstring(xml)), expect)

    def test_sorted_work_editions(self):
        json_data = '''{
 "responseHeader":{
  "status":0,
  "QTime":1,
  "params":{
    "fl":"edition_key",
    "indent":"on",
    "wt":"json",
    "q":"key:OL100000W"}},
 "response":{"numFound":1,"start":0,"docs":[
    {
     "edition_key":["OL7536692M","OL7825368M","OL3026366M"]}]
 }}'''
        expect = ["OL7536692M","OL7825368M","OL3026366M"]
        self.assertEqual(sorted_work_editions('OL100000W', json_data=json_data), expect)
        
    def test_query_parser_fields(self):
        func = parse_query_fields

        expect = [('text', 'query here')]
        q = 'query here'
        print q
        self.assertEqual(list(func(q)), expect)

        expect = [('title', 'food rules'), ('author_name', 'pollan')]

        q = 'title:food rules author:pollan'
        self.assertEqual(list(func(q)), expect)

        q = 'title:food rules by:pollan'
        self.assertEqual(list(func(q)), expect)

        q = 'Title:food rules By:pollan'
        self.assertEqual(list(func(q)), expect)

        expect = [('title', '"food rules"'), ('author_name', 'pollan')]
        q = 'title:"food rules" author:pollan'
        self.assertEqual(list(func(q)), expect)

        expect = [('text', 'query here'), ('title', 'food rules'), ('author_name', 'pollan')]
        q = 'query here title:food rules author:pollan'
        self.assertEqual(list(func(q)), expect)

        expect = [('text', 'flatland\:a romance of many dimensions')]
        q = 'flatland:a romance of many dimensions'
        self.assertEqual(list(func(q)), expect)

        expect = [('title', 'flatland\:a romance of many dimensions')]
        q = 'title:flatland:a romance of many dimensions'
        self.assertEqual(list(func(q)), expect)
