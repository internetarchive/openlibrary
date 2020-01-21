# -*- coding: UTF-8 -*-
import os
import pytest

from openlibrary.catalog.marc.fast_parse import index_fields, get_tag_lines, read_edition

test_data = "%s/test_data/bin_input/" % os.path.dirname(__file__)

@pytest.mark.skip
def test_read_oclc():
    # DEPRECATED data was 'oregon_27194315', triggers exception
    for f in ('scrapbooksofmoun03tupp_meta.mrc',):
        data = open(test_data + f).read()
        i = index_fields(data, ['001', '003', '010', '020', '035', '245'])
        assert 'oclc' in i
        e = read_edition(data)
        assert 'oclc' in e

@pytest.mark.skip
def test_ia_charset():
    # Tests a corrupted unicode MARC record is corrected, does code exist to fix this?
    data = open(test_data + 'histoirereligieu05cr_meta.mrc').read()
    line = list(get_tag_lines(data, set(['100'])))[0][1]
    a = list(get_all_subfields(line))[0][1]
    expect = u'Crétineau-Joly, J.'
    assert a == expect
