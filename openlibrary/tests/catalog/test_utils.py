# -*- coding: utf-8 -*-

import pytest
from openlibrary.catalog.utils import (
    author_dates_match, flip_name,
    pick_first_date, pick_best_name, pick_best_author,
    match_with_bad_chars, mk_norm, strip_count,
    remove_trailing_dot)

def test_author_dates_match():
    _atype = {'key': '/type/author'}
    basic = {'name': 'John Smith', 'death_date': '1688', 'key': '/a/OL6398451A', 'birth_date': '1650', 'type': _atype}
    full_dates = {'name': 'John Smith', 'death_date': '23 June 1688', 'key': '/a/OL6398452A', 'birth_date': '01 January 1650', 'type': _atype}
    full_different = {'name': 'John Smith', 'death_date': '12 June 1688', 'key': '/a/OL6398453A', 'birth_date': '01 December 1650', 'type': _atype}
    no_death = {'name': 'John Smith', 'key': '/a/OL6398454A', 'birth_date': '1650', 'type': _atype}
    no_dates = {'name': 'John Smith', 'key': '/a/OL6398455A', 'type': _atype}
    non_match = {'name': 'John Smith', 'death_date': u'1999', 'key': '/a/OL6398456A', 'birth_date': '1950', 'type': _atype}
    different_name = {'name': 'Jane Farrier', 'key': '/a/OL6398457A', 'type': _atype}

    assert author_dates_match(basic, basic)
    assert author_dates_match(basic, full_dates)
    assert author_dates_match(basic, no_death)
    assert author_dates_match(basic, no_dates)
    assert author_dates_match(no_dates, no_dates)
    assert author_dates_match(no_dates, non_match)  # Without dates, the match returns True
    assert author_dates_match(no_dates, different_name)  # This method only compares dates and ignores names
    assert author_dates_match(basic, non_match) is False
    # FIXME: the following should properly be False:
    assert author_dates_match(full_different, full_dates) # this shows matches are only occurring on year, full dates are ignored!

def test_flip_name():
    assert flip_name('Smith, John.') == 'John Smith'
    assert flip_name('Smith, J.') == 'J. Smith'
    assert flip_name('No comma.') == 'No comma'

def test_pick_first_date():
    assert pick_first_date(["Mrs.", "1839-"]) == {'birth_date': '1839'}
    assert pick_first_date(["1882-."]) == {'birth_date': '1882'}
    assert pick_first_date(["1900-1990.."]) == {'birth_date': u'1900', 'death_date': u'1990'}
    assert pick_first_date(["4th/5th cent."]) == {'date': '4th/5th cent.'}

def test_pick_best_name():
    names = [u'Andre\u0301 Joa\u0303o Antonil', u'Andr\xe9 Jo\xe3o Antonil', 'Andre? Joa?o Antonil']
    best = names[1]
    assert pick_best_name(names) == best

    names = [u'Antonio Carvalho da Costa', u'Anto\u0301nio Carvalho da Costa', u'Ant\xf3nio Carvalho da Costa']
    best = names[2]
    assert pick_best_name(names) == best

def test_pick_best_author():
    a1 = {u'name': u'Bretteville, Etienne Dubois abb\xe9 de', u'death_date': u'1688', 'key': u'/a/OL6398452A', u'birth_date': u'1650', u'title': u'abb\xe9 de', u'personal_name': u'Bretteville, Etienne Dubois', u'type': {u'key': u'/type/author'}, }
    a2 = {u'name': u'Bretteville, \xc9tienne Dubois abb\xe9 de', u'death_date': u'1688', u'key': u'/a/OL4953701A', u'birth_date': u'1650', u'title': u'abb\xe9 de', u'personal_name': u'Bretteville, \xc9tienne Dubois', u'type': {u'key': u'/type/author'}, }
    assert pick_best_author([a1, a2])['key'] == a2['key']

def combinations(items, n):
    if n==0:
        yield []
    else:
        for i in range(len(items)):
            for cc in combinations(items[i+1:], n-1):
                yield [items[i]]+cc

def test_match_with_bad_chars():
    samples = [
        [u'Machiavelli, Niccolo, 1469-1527', u'Machiavelli, Niccol\xf2 1469-1527'],
        [u'Humanitas Publica\xe7\xf5es', 'Humanitas Publicac?o?es'],
        [u'A pesquisa ling\xfc\xedstica no Brasil',
          'A pesquisa lingu?i?stica no Brasil'],
        [u'S\xe3o Paulo', 'Sa?o Paulo'],
        [u'Diccionario espa\xf1ol-ingl\xe9s de bienes ra\xedces',
         u'Diccionario Espan\u0303ol-Ingle\u0301s de bienes rai\u0301ces'],
        [u'Konfliktunterdru?ckung in O?sterreich seit 1918',
         u'Konfliktunterdru\u0308ckung in O\u0308sterreich seit 1918',
         u'Konfliktunterdr\xfcckung in \xd6sterreich seit 1918'],
        [u'Soi\ufe20u\ufe21z khudozhnikov SSSR.',
         u'Soi?u?z khudozhnikov SSSR.',
         u'Soi\u0361uz khudozhnikov SSSR.'],
        [u'Andrzej Weronski', u'Andrzej Wero\u0144ski', u'Andrzej Weron\u0301ski'],
    ]
    for l in samples:
        for a, b in combinations(l, 2):
            assert match_with_bad_chars(a, b)

def test_strip_count():
    input = [
        ('Side by side', [ u'a', u'b', u'c', u'd' ]),
        ('Side by side.', [ u'e', u'f', u'g' ]),
        ('Other.', [ u'h', u'i' ]),
    ]
    expect = [
        ('Side by side', [ u'a', u'b', u'c', u'd', u'e', u'f', u'g' ]),
        ('Other.', [ u'h', u'i' ]),
    ]
    assert strip_count(input) == expect

def test_remove_trailing_dot():
    data = [
        ('Test', 'Test'),
        ('Test.', 'Test'),
        ('Test J.', 'Test J.'),
        ('Test...', 'Test...'),
        #('Test Jr.', 'Test Jr.'),
    ]
    for input, expect in data:
        output = remove_trailing_dot(input)
        assert output == expect

mk_norm_conversions = [
        ("Hello I'm a  title.", "helloi'matitle"),
        (u"Hello I'm a  title.", "helloi'matitle"),
        ('Forgotten Titles: A Novel.', 'forgottentitlesanovel'),
        (u'Kitāb Yatīmat ud-Dahr', u'kitābyatīmatuddahr'),
]

@pytest.mark.parametrize('title,expected', mk_norm_conversions)
def test_mk_norm(title, expected):
    assert mk_norm(title) == expected
