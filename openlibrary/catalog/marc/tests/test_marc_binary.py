# -*- coding: UTF-8 -*-
from openlibrary.catalog.marc.marc_binary import BinaryDataField 

class MockMARC:
    def __init__(self, leader_9):
        # 'a' for utf-8, ' ' for MARC8
        self.leader_9 = leader_9

    def leader(self):
        return '#' * 9 + self.leader_9

class Test_BinaryDataField:
    def test_translate(self):
        bdf = BinaryDataField(MockMARC(' '), '')
        assert bdf.translate('Vieira, Claudio Bara\xe2una,') == u'Vieira, Claudio Baraúna,'

    def test_bad_marc_line(self):
        line = '0 \x1f\xe2aEtude objective des ph\xe2enom\xe1enes neuro-psychiques;\x1e'
        bdf = BinaryDataField(MockMARC(' '), line)
        assert list(bdf.get_all_subfields()) == [(u'á', u'Etude objective des phénomènes neuro-psychiques;')]
