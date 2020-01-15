# -*- coding: UTF-8 -*-
import os

from openlibrary.catalog.marc.marc_binary import BinaryDataField, handle_wrapped_lines
from openlibrary.catalog.marc.fast_parse import get_tag_lines  # Deprecated import

test_data = "%s/test_data/bin_input/" % os.path.dirname(__file__)

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


def test_wrapped_lines():
    data = open(test_data + 'wrapped_lines').read()
    ret = list(handle_wrapped_lines(get_tag_lines(data, ['520'])))
    assert len(ret) == 2
    a, b = ret
    assert a[0] == '520' and b[0] == '520'
    assert len(a[1]) == 2295
    assert len(b[1]) == 248
