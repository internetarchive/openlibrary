#!/usr/bin/python

import unittest
from parse import normalize_isbn, biggest_decimal, compile_marc_spec

class MockField:
    def __init__(self, subfields):
        self.subfield_sequence = subfields
        self.contents = {}
        for k, v in subfields:
            self.contents.setdefault(k, []).append(v)
    def get_elts(self, i):
        if i in self.contents:
            return self.contents[i]
        else:
            return []
class MockRecord:
    def __init__(self, subfields):
        self.field = MockField(subfields)
    def get_fields(self, tag):
        return [self.field]

class TestMarcParse(unittest.TestCase):
    def test_normalize_isbn(self):
        data = [
            ('0300067003 (cloth : alk. paper)', '0300067003'),
            ('0197263771 (cased)', '0197263771'),
            ('8831789589 (pbk.)', '8831789589'),
            ('9788831789585 (pbk.)', '9788831789585'),
            ('1402051891 (hd.bd.)', '1402051891'),
            ('9061791308', '9061791308'),
            ('9788831789530', '9788831789530'),
            ('8831789538', '8831789538'),
            ('97883178953X ', '97883178953X'),
            ('0-14-118250-4', '0141182504'),
            ('0321434250 (textbook)', '0321434250'),
        ]

        for (input, expect) in data:
            output = normalize_isbn(input)
            self.assertEqual(expect.lower(), output.lower())

    def test_biggest_decimal(self):
        data = [
            ("xx, 1065 , [57] p. :", '1065'),
            ("193 p., 31 p. of plates", '193'),
        ]
        for (input, expect) in data:
            output = biggest_decimal(input)
            self.assertEqual(output, expect)

    def xtest_subject_order(self):
        gen = compile_marc_spec('650:a--x--v--y--z')

        data = [
            ([  ('a', 'Authors, American'),
                ('y', '19th century'),
                ('x', 'Biography.')],
                'Authors, American -- 19th century -- Biography.'),
            ([  ('a', 'Western stories'),
                ('x', 'History and criticism.')],
                'Western stories -- History and criticism.'),
            ([  ('a', 'United States'),
                ('x', 'History'),
                ('y', 'Revolution, 1775-1783'),
                ('x', 'Influence.')],
                'United States -- History -- Revolution, 1775-1783 -- Influence.'
            ),
            ([  ('a', 'West Indies, British'),
                ('x', 'History'),
                ('y', '18th century.')],
                'West Indies, British -- History -- 18th century.'),
            ([  ('a', 'Great Britain'),
                ('x', 'Relations'),
                ('z', 'West Indies, British.')],
                'Great Britain -- Relations -- West Indies, British.'),
            ([  ('a', 'West Indies, British'),
                ('x', 'Relations'),
                ('z', 'Great Britain.')],
                'West Indies, British -- Relations -- Great Britain.')
        ]
        for (input, expect) in data:
            output = [i for i in gen(MockRecord(input))]
            self.assertEqual([expect], output)

    def test_title(self):
        gen = compile_marc_spec('245:ab clean_name')
        data = [
            ([  ('a', 'Railroad construction.'),
                ('b', 'Theory and practice.  A textbook for the use of students in colleges and technical schools.'),
                ('b', 'By Walter Loring Webb.')],
                'Railroad construction. Theory and practice.  A textbook for the use of students in colleges and technical schools. By Walter Loring Webb.')
        ]

        for (input, expect) in data:
            output = [i for i in gen(MockRecord(input))]
            self.assertEqual([expect], output)
    def test_by_statement(self):
        gen = compile_marc_spec('245:c')
        data = [
            ([  ('a', u'Trois contes de No\u0308el'),
                ('c', u'[par] Madame Georges Renard,'),
                ('c', u'edited by F. Th. Meylan ...')],
                '[par] Madame Georges Renard, edited by F. Th. Meylan ...')
        ]
        for (input, expect) in data:
            output = [i for i in gen(MockRecord(input))]
            self.assertEqual([expect], output)

if __name__ == '__main__':
    unittest.main()
