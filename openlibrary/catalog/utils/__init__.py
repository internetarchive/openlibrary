# -*- coding: utf-8 -*-
import re, web
from unicodedata import normalize
import openlibrary.catalog.merge.normalize as merge

re_date = map (re.compile, [
    '(?P<birth_date>\d+\??)-(?P<death_date>\d+\??)',
    '(?P<birth_date>\d+\??)-',
    'b\.? (?P<birth_date>(?:ca\. )?\d+\??)',
    'd\.? (?P<death_date>(?:ca\. )?\d+\??)',
    '(?P<birth_date>.*\d+.*)-(?P<death_date>.*\d+.*)',
    '^(?P<birth_date>[^-]*\d+[^-]+ cent\.[^-]*)$'])

re_ad_bc = re.compile(r'\b(B\.C\.?|A\.D\.?)')
re_date_fl = re.compile('^fl[., ]')
re_number_dot = re.compile('\d{2,}[- ]*(\.+)$')
re_l_in_date = re.compile('(l\d|\dl)')
re_end_dot = re.compile('[^ .][^ .]\.$', re.UNICODE)
re_marc_name = re.compile('^(.*?),+ (.*)$')
re_year = re.compile(r'\b(\d{4})\b')

re_brackets = re.compile('^(.+)\[.*?\]$')

def key_int(rec):
    # extract the number from a key like /a/OL1234A
    return int(web.numify(rec['key']))

def author_dates_match(a, b):
    # check if the dates of two authors
    for k in ['birth_date', 'death_date', 'date']:
        if k not in a or a[k] is None or k not in b or b[k] is None:
            continue
        if a[k] == b[k] or a[k].startswith(b[k]) or b[k].startswith(a[k]):
            continue
        m1 = re_year.search(a[k])
        if not m1:
            return False
        m2 = re_year.search(b[k])
        if m2 and m1.group(1) == m2.group(1):
            continue
        return False
    return True

def flip_name(name):
    # strip end dots like this: "Smith, John." but not like this: "Smith, J."
    m = re_end_dot.search(name)
    if m:
        name = name[:-1]

    if name.find(', ') == -1:
        return name
    m = re_marc_name.match(name)
    return m.group(2) + ' ' + m.group(1)

def remove_trailing_number_dot(date):
    m = re_number_dot.search(date)
    if m:
        return date[:-len(m.group(1))]
    else:
        return date

def remove_trailing_dot(s):
    if s.endswith(" Dept."):
        return s
    m = re_end_dot.search(s)
    if m:
        s = s[:-1]
    return s

def fix_l_in_date(date):
    if not 'l' in date:
        return date
    return re_l_in_date.sub(lambda m:m.group(1).replace('l', '1'), date)

re_ca = re.compile('ca\.([^ ])')

def parse_date(date):
    if re_date_fl.match(date):
        return {}
    date = remove_trailing_number_dot(date)
    date = re_ca.sub(lambda m:'ca. ' + m.group(1), date)
    if date.find('-') == -1:
        for r in re_date:
            m = r.search(date)
            if m:
                return dict((k, fix_l_in_date(v)) for k, v in m.groupdict().items())
        return {}

    parts = date.split('-')
    i = { 'birth_date': parts[0].strip() }
    if len(parts) == 2:
        parts[1] = parts[1].strip()
        if parts[1]:
            i['death_date'] = fix_l_in_date(parts[1])
            if not re_ad_bc.search(i['birth_date']):
                m = re_ad_bc.search(i['death_date'])
                if m:
                    i['birth_date'] += ' ' + m.group(1)
    if 'birth_date' in i and 'l' in i['birth_date']:
        i['birth_date'] = fix_l_in_date(i['birth_date'])
    return i

re_cent = re.compile('^[\dl][^-]+ cent\.$')

def pick_first_date(dates):
    # this is to handle this case:
    # 100: $aLogan, Olive (Logan), $cSikes, $dMrs., $d1839-
    # see http://archive.org/download/gettheebehindmes00logaiala/gettheebehindmes00logaiala_meta.mrc
    # or http://pharosdb.us.archive.org:9090/show-marc?record=gettheebehindmes00logaiala/gettheebehindmes00logaiala_meta.mrc:0:521

    dates = list(dates)
    if len(dates) == 1 and re_cent.match(dates[0]):
        return { 'date': fix_l_in_date(dates[0]) }

    for date in dates:
        result = parse_date(date)
        if result != {}:
            return result

    return { 'date': fix_l_in_date(' '.join([remove_trailing_number_dot(d) for d in dates])) }

def test_date():
    assert pick_first_date(["Mrs.", "1839-"]) == {'birth_date': '1839'}
    assert pick_first_date(["1882-."]) == {'birth_date': '1882'}
    assert pick_first_date(["1900-1990.."]) == {'birth_date': u'1900', 'death_date': u'1990'}
    assert pick_first_date(["4th/5th cent."]) == {'date': '4th/5th cent.'}

def strip_accents(s):
    return normalize('NFKD', unicode(s)).encode('ASCII', 'ignore')

def combinations(items, n):
    if n==0:
        yield []
    else:
        for i in xrange(len(items)):
            for cc in combinations(items[i+1:], n-1):
                yield [items[i]]+cc

re_drop = re.compile('[?,]')

def match_with_bad_chars(a, b):
    if unicode(a) == unicode(b):
        return True
    a = normalize('NFKD', unicode(a)).lower()
    b = normalize('NFKD', unicode(b)).lower()
    if a == b:
        return True
    a = a.encode('ASCII', 'ignore')
    b = b.encode('ASCII', 'ignore')
    if a == b:
        return True
    def drop(s):
        return re_drop.sub('', s)
    return drop(a) == drop(b)

def accent_count(s):
    return len([c for c in norm(s) if ord(c) > 127])

def norm(s):
    return normalize('NFC', s) if isinstance(s, unicode) else s

def pick_best_name(names):
    names = [norm(n) for n in names]
    n1 = names[0]
    assert all(match_with_bad_chars(n1, n2) for n2 in names[1:])
    names.sort(key=lambda n:accent_count(n), reverse=True)
    assert '?' not in names[0]
    return names[0]

def pick_best_author(authors):
    n1 = authors[0]['name']
    assert all(match_with_bad_chars(n1, a['name']) for a in authors[1:])
    authors.sort(key=lambda a:accent_count(a['name']), reverse=True)
    assert '?' not in authors[0]['name']
    return authors[0]

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

def test_match_with_bad_chars():
    samples = [
        [u'Machiavelli, Niccolo, 1469-1527', u'Machiavelli, Niccol\xf2 1469-1527'],
        [u'Humanitas Publica\xe7\xf5es', 'Humanitas Publicac?o?es'],
        [u'A pesquisa ling\xfc\xedstica no Brasil',
          'A pesquisa lingu?i?stica no Brasil'],
        [u'S\xe3o Paulo', 'Sa?o Paulo'],
        [u'Diccionario espa\xf1ol-ingl\xe9s de bienes ra\xedces',
         u'Diccionario Espan\u0303ol-Ingle\u0301s de bienes rai\u0301lces'],
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
#            print a, len(a)
#            print b, len(b)
            assert match_with_bad_chars(a, b)

def tidy_isbn(input):
    output = []
    for i in input:
        i = i.replace('-', '')
        if len(i) in (10, 13):
            output.append(i)
            continue
        if len(i) == 20 and all(c.isdigit() for c in i):
            output.extend([i[:10], i[10:]])
            continue
        if len(i) == 21 and not i[10].isdigit():
            output.extend([i[:10], i[11:]])
            continue
        if i.find(';') != -1:
            no_semicolon = i.replace(';', '')
            if len(no_semicolon) in (10, 13):
                output.append(no_semicolon)
                continue
            split = i.split(';')
            if all(len(j) in (10, 13) for j in split):
                output.extend(split)
                continue
        output.append(i)
    return output

def strip_count(counts):
    foo = {}
    for i, j in counts:
        foo.setdefault(i.rstrip('.').lower() if isinstance(i, basestring) else i, []).append((i, j))
    ret = {}
    for k, v in foo.iteritems():
        m = max(v, key=lambda x: len(x[1]))[0]
        bar = []
        for i, j in v:
            bar.extend(j)
        ret[m] = bar
    return sorted(ret.iteritems(), cmp=lambda x,y: cmp(len(y[1]), len(x[1]) ))

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
        ('Test...', 'Test...')
    ]
    for input, expect in data:
        output = remove_trailing_dot(input)
        assert output == expect

def fmt_author(a):
    if 'birth_date' in a or 'death_date' in a:
        return "%s (%s-%s)" % ( a['name'], a.get('birth_date', ''), a.get('death_date', '') )
    return a['name']

def get_title(e):
    if e.get('title_prefix', None) is not None:
        prefix = e['title_prefix']
        if prefix[-1] != ' ':
            prefix += ' '
        title = prefix + e['title']
    else:
        title = e['title']
    return title

def mk_norm(title):
    m = re_brackets.match(title)
    if m:
        title = m.group(1)
    norm = merge.normalize(title).strip(' ')
    norm = norm.replace(' and ', ' ')
    if norm.startswith('the '):
        norm = norm[4:]
    elif norm.startswith('a '):
        norm = norm[2:]
    return norm.replace('-', '').replace(' ', '')
