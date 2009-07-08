import re, unicodedata 

#re_brace = re.compile('{[^{}]+?}')
re_normalize = re.compile('[^\w ]')
re_whitespace = re.compile('[-\s,;.]+')

def normalize(s):
    if isinstance(s, unicode):
        s = unicodedata.normalize('NFC', s.replace(u'\u0142', u'l'))
    s = s.replace(' & ', ' and ')
    # remove {mlrhring} and friends
    # see http://www.loc.gov/marc/mnemonics.html
    # s = re_brace.sub('', s)
    s = re_whitespace.sub(' ', s.lower())
    s = re_normalize.sub('', s.strip())
    return s

#def test_normalize():
#    a = "The La{dotb}t{macr}a{mlrhring}if al-ma{mllhring}{macr}arif of Tha{mllhring} {macr}alibi. The book of curious and entertaining information"
#    b = u"The La\xf2t\xe5a\xaeif al-ma\xb0\xe5arif of Tha\xb0 \xe5alibi. The book of curious and entertaining information"
#    assert normalize(a) == normalize(b)
#
#    a = "Tha{mllhring}{macr}alib{macr}i, {mllhring}Abd al-Malik ibn Mu{dotb}hammad 961 or 2-1037 or 8."
#    b = u"Tha\xb0\xe5alib\xe5i, \xb0Abd al-Malik ibn Mu\xf2hammad 961 or 2-1037 or 8."
#    assert normalize(a) == normalize(b)

