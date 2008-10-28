import re

re_marc_name = re.compile('^(.*), (.*)$')
re_initial_then_dot = re.compile(r'\b[A-Z]\.')

def flip_name(name):
    m = re_marc_name.match(name)
    return m.group(2) + ' ' + m.group(1)

def pick_name(a, b):
    if re_initial_then_dot.search(a):
        return flip_name(a)
    else:
        return b

def east_in_by_statement(name, by_statements):
    assert name.find(', ') != -1
    name = name.replace('.', '')
    flipped = flip_name(name)
    name = name.replace(', ', ' ')
    if name == flipped:
        return False
    for by in by_statements:
        if by.find(name) != -1:
            return True
    return False

def test_merge():
    data = [
        (u'Hood, Christopher', u'Christopher Hood', u'Christopher Hood'),
        (u'Pawsey, Margaret M.', u'Margaret M Pawsey', u'Margaret M. Pawsey'),
        (u'Elchardus, M.', u'M Elchardus', u'M. Elchardus'),
        (u'Hayes, Mike.', u'Mike Hayes', u'Mike Hayes'),
        (u'Krause, Rainer.', u'Rainer Krause', u'Rainer Krause'),
        (u'Hoffmann, Manfred.', u'Manfred Hoffmann', u'Manfred Hoffmann'),
        (u'Masson, Veneta.', u'Veneta Masson', u'Veneta Masson'),
        (u'Baker, Ernest.', u'Ernest Baker', u'Ernest Baker'),
        (u'Hooper, James.', u'James Hooper', u'James Hooper'),
        (u'Bront\xeb, Charlotte', u'Charlotte Bront\xeb', u'Charlotte Bront\xeb'),
        (u'Nichols, Francis Henry', u'Francis Henry Nichols', u'Francis Henry Nichols'),
        (u'Becker, Bernd', u'Bernd Becker', u'Bernd Becker'),
        (u'Sadleir, Richard.', u'Richard Sadleir', u'Richard Sadleir'),
    ]
    for a, b, want in data:
        assert pick_name(a, b) == want

    assert east_in_by_statement("Wang, Qi", ["Wang Qi."])
    assert not east_in_by_statement("Walker, Charles L.",\
            ["edited by A. Karl Larson and Katharine Miles Larson."])
    assert not east_in_by_statement("Luoma, Gary A.", ["Gary A. Luoma"])
    assert not east_in_by_statement("Tan, Tan", ["Tan Tan zhu.", "Tan Tan zhu.", "Tan Tan ; [cha tu Li Ruguang ; ze ren bian ji Wang Zhengxiang]."])
