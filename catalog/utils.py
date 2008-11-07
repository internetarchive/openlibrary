import re
# -*- coding: utf-8 -*-

re_date = map (re.compile, [
    '(?P<birth_date>\d+\??)-(?P<death_date>\d+\??)',
    '(?P<birth_date>\d+\??)-',
    'b\.? (?P<birth_date>(?:ca\. )?\d+\??)',
    'd\.? (?P<death_date>(?:ca\. )?\d+\??)',
    '(?P<birth_date>.*\d+.*)-(?P<death_date>.*\d+.*)',
    '^(?P<birth_date>[^-]*\d+[^-]+ cent\.[^-]*)$'])

re_ad_bc = re.compile(r'\b(B\.C\.?|A\.D\.?)')
re_date_fl = re.compile('^fl[., ]')
re_number_dot = re.compile('\d{3,}\.$')

def remove_trailing_number_dot(date):
    m = re_number_dot.search(date)
    if m:
        return date[:-1]
    else:
        return date

def parse_date(date):
    if re_date_fl.match(date):
        return {}
    if date.find('-') == -1:
        for r in re_date:
            m = r.search(date)
            if m:
                return m.groupdict()
        return {}

    parts = date.split('-')
    i = { 'birth_date': parts[0].strip() }
    if len(parts) == 2:
        parts[1] = parts[1].strip()
        if parts[1]:
            i['death_date'] = parts[1]
            if not re_ad_bc.search(i['birth_date']):
                m = re_ad_bc.search(i['death_date'])
                if m:
                    i['birth_date'] += ' ' + m.group(1)
    return i

def pick_first_date(dates):
    # this is to handle this case:
    # 100: $aLogan, Olive (Logan), $cSikes, $dMrs., $d1839-
    # see http://archive.org/download/gettheebehindmes00logaiala/gettheebehindmes00logaiala_meta.mrc
    # or http://pharosdb.us.archive.org:9090/show-marc?record=gettheebehindmes00logaiala/gettheebehindmes00logaiala_meta.mrc:0:521

    for date in dates:
        result = parse_date(date)
        if result != {}:
            return result

    return { 'date': ' '.join([remove_trailing_number_dot(d) for d in dates]) }

def test_date():
    assert pick_first_date(["Mrs.", "1839-"]) == {'birth_date': '1839'}

def test_match_with_bad_chars():
    samples = [
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
    ]
    for a, b in samples:
        assert match_with_bad_chars(a, b)
        assert match_with_bad_chars(b, a)
