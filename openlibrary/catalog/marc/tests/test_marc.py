import unittest
from openlibrary.catalog.marc.get_subjects import subjects_for_work
from openlibrary.catalog.marc.marc_base import MarcBase
from openlibrary.catalog.marc.parse import read_isbn, read_pagination, read_title

class MockField:
    def __init__(self, subfields):
        self.subfield_sequence = subfields
        self.contents = {}
        for k, v in subfields:
            self.contents.setdefault(k, []).append(v)

    def get_contents(self, want):
        contents = {}
        for k, v in self.get_subfields(want):
            if v:
                contents.setdefault(k, []).append(v)
        return contents

    def get_all_subfields(self):
        return self.get_subfields(self.contents.keys())

    def get_subfields(self, want):
        for w in want:
           if w in self.contents:
               for i in self.contents.get(w):
                   yield w, i

    def get_subfield_values(self, want):
        return [v for k, v in self.get_subfields(want)]

class MockRecord(MarcBase):
    """ usage: MockRecord('020', [('a', 'value'), ('c', 'value'), ('c', 'value')])
        Currently only supports a single tag per Record."""
    def __init__(self, marc_field, subfields):
        self.tag = marc_field
        self.field = MockField(subfields)

    def decode_field(self, field):
        return field

    def read_fields(self, want):
        if self.tag in want:
            yield self.tag, self.field

    def get_fields(self, tag):
        if tag == self.tag:
            return [self.field]

class TestMarcParse(unittest.TestCase):
    def test_read_isbn(self):
        data = [
            ('0300067003 (cloth : alk. paper)', '0300067003'),
            ('0197263771 (cased)', '0197263771'),
            ('8831789589 (pbk.)', '8831789589'),
            ('9788831789585 (pbk.)', '9788831789585'),
            ('1402051891 (hd.bd.)', '1402051891'),
            ('9061791308', '9061791308'),
            ('9788831789530', '9788831789530'),
            ('8831789538', '8831789538'),
            ('0-14-118250-4', '0141182504'),
            ('0321434250 (textbook)', '0321434250'),
            # 12 character ISBNs currently get assigned to isbn_10
            # unsure whether this is a common / valid usecase:
            ('97883178953X ', '97883178953X'),
        ]

        for (value, expect) in data:
            rec = MockRecord('020', [('a', value)])
            output = read_isbn(rec)
            if len(expect) == 13:
                isbn_type = 'isbn_13'
            else:
                isbn_type = 'isbn_10'
            self.assertEqual(expect, output[isbn_type][0])

    def test_read_pagination(self):
        data = [
            ('xx, 1065 , [57] p.', 1065),
            ('193 p., 31 p. of plates', 193),
        ]
        for (value, expect) in data:
            rec = MockRecord('300', [('a', value)])
            output = read_pagination(rec)
            self.assertEqual(output['number_of_pages'], expect)
            self.assertEqual(output['pagination'], value)

    def test_subjects_for_work(self):
        data = [
            ([  ('a', 'Authors, American'),
                ('y', '19th century'),
                ('x', 'Biography.')],
                {'subject_times': ['19th century'],
                 'subjects': ['American Authors', 'Biography']}),
            ([  ('a', 'Western stories'),
                ('x', 'History and criticism.')],
                {'subjects': ['Western stories', 'History and criticism']}),
            ([  ('a', 'United States'),
                ('x', 'History'),
                ('y', 'Revolution, 1775-1783'),
                ('x', 'Influence.')],
                # TODO: this expectation does not capture the intent or ordering of the original MARC, investigate x subfield!
                {'subject_times': ['Revolution, 1775-1783'], 'subjects': ['United States', 'Influence', 'History']}),
                # 'United States -- History -- Revolution, 1775-1783 -- Influence.'
            ([  ('a', 'West Indies, British'),
                ('x', 'History'),
                ('y', '18th century.')],
                {'subject_times': ['18th century'], 'subjects': ['British West Indies', 'History']}),
                # 'West Indies, British -- History -- 18th century.'),
            ([  ('a', 'Great Britain'),
                ('x', 'Relations'),
                ('z', 'West Indies, British.')],
                {'subject_places': ['British West Indies'], 'subjects': ['Great Britain', 'Relations']}),
                #'Great Britain -- Relations -- West Indies, British.'),
            ([  ('a', 'West Indies, British'),
                ('x', 'Relations'),
                ('z', 'Great Britain.')],
                {'subject_places': ['Great Britain'], 'subjects': ['British West Indies', 'Relations']})
                #'West Indies, British -- Relations -- Great Britain.')
        ]
        for (value, expect) in data:
            output = subjects_for_work(MockRecord('650', value))
            self.assertEqual(expect, output)

    def test_read_title(self):
        data = [
            ([  ('a', 'Railroad construction.'),
                ('b', 'Theory and practice.'),
                ('b', 'A textbook for the use of students in colleges and technical schools.')],
                {'title': 'Railroad construction',
                # TODO: Investigate whether this colon between subtitles is spaced correctly
                 'subtitle': 'Theory and practice : A textbook for the use of students in colleges and technical schools'})
        ]

        for (value, expect) in data:
            output = read_title(MockRecord('245', value))
            self.assertEqual(expect, output)

    def test_by_statement(self):
        data = [
            ([  ('a', u'Trois contes de No\u0308el'),
                ('c', u'[par] Madame Georges Renard,'),
                ('c', u'edited by F. Th. Meylan ...')],
                {'title': u'Trois contes de No\u0308el', 'by_statement': '[par] Madame Georges Renard, edited by F. Th. Meylan ...'})
        ]
        for (value, expect) in data:
            output = read_title(MockRecord('245', value))
            self.assertEqual(expect, output)
