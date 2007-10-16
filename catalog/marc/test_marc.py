#!/usr/bin/python

import unittest
from parse import normalize_isbn

class TestMarcParse(unittest.TestCase):
    def test_normalize_isbn(self):
        samples = [
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

        for (input, expect) in samples:
            output = normalize_isbn(input)
            self.assertEqual(expect.lower(), output.lower())

if __name__ == '__main__':
    unittest.main()
