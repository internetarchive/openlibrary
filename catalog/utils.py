import re

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
