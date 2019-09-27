# -*- coding: utf-8 -*-
import pytest
from openlibrary.catalog.merge.normalize import normalize

def test_normalize():
    assert normalize('Hello this is a           Title') == 'hello this is a title'

def test_normalize_titles_with_and():
    a = 'This and That'
    b = 'This & that'
    norm = "this and that"
    assert normalize(a) == normalize(b)
    assert normalize(b) == norm

def test_normalize_unicode():
    a = u'Kitāb Yatīmat ud-Dahr' 
    assert normalize(a) == u'kitāb yatīmat ud dahr'

@pytest.mark.skip(reason="Stripping these mnemonics is not implemented. Unsure whether this is a current problem with titles.")
def test_normalize_replace_MARCMaker_mnemonics():
    # see http://www.loc.gov/marc/mnemonics.html
    a = "The La{dotb}t{macr}a{mlrhring}if al-ma{mllhring}{macr}arif of Tha{mllhring} {macr}alibi. The book of curious and entertaining information"
    b = u"The La\xf2t\xe5a\xaeif al-ma\xb0\xe5arif of Tha\xb0 \xe5alibi. The book of curious and entertaining information"
    assert normalize(a) == normalize(b)

    a = "Tha{mllhring}{macr}alib{macr}i, {mllhring}Abd al-Malik ibn Mu{dotb}hammad 961 or 2-1037 or 8."
    b = u"Tha\xb0\xe5alib\xe5i, \xb0Abd al-Malik ibn Mu\xf2hammad 961 or 2-1037 or 8."
    assert normalize(a) == normalize(b)
