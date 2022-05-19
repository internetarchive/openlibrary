import re
import web
from unicodedata import normalize
import openlibrary.catalog.merge.normalize as merge


def cmp(x, y):
    return (x > y) - (x < y)


re_date = map(
    re.compile,  # type: ignore[arg-type]
    [
        r'(?P<birth_date>\d+\??)-(?P<death_date>\d+\??)',
        r'(?P<birth_date>\d+\??)-',
        r'b\.? (?P<birth_date>(?:ca\. )?\d+\??)',
        r'd\.? (?P<death_date>(?:ca\. )?\d+\??)',
        r'(?P<birth_date>.*\d+.*)-(?P<death_date>.*\d+.*)',
        r'^(?P<birth_date>[^-]*\d+[^-]+ cent\.[^-]*)$',
    ],
)

re_ad_bc = re.compile(r'\b(B\.C\.?|A\.D\.?)')
re_date_fl = re.compile('^fl[., ]')
re_number_dot = re.compile(r'\d{2,}[- ]*(\.+)$')
re_l_in_date = re.compile(r'(l\d|\dl)')
re_end_dot = re.compile(r'[^ .][^ .]\.$', re.UNICODE)
re_marc_name = re.compile('^(.*?),+ (.*)$')
re_year = re.compile(r'\b(\d{4})\b')

re_brackets = re.compile(r'^(.+)\[.*?\]$')


def key_int(rec):
    # extract the number from a key like /a/OL1234A
    return int(web.numify(rec['key']))


def author_dates_match(a, b):
    """
    Checks if the years of two authors match. Only compares years,
    not names or keys. Works by returning False if any year specified in one record
    does not match that in the other, otherwise True. If any one author does not have
    dates, it will return True.

    :param dict a: Author import dict {"name": "Some One", "birth_date": "1960"}
    :param dict b: Author import dict {"name": "Some One"}
    :rtype: bool
    """
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
    """
    Flip author name about the comma, stripping the comma, and removing non
    abbreviated end dots. Returns name with end dot stripped if no comma+space found.
    The intent is to convert a Library indexed name to natural name order.

    :param str name: e.g. "Smith, John." or "Smith, J."
    :rtype: str
    :return: e.g. "John Smith" or "J. Smith"
    """

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
        return date[: -len(m.group(1))]
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
    return re_l_in_date.sub(lambda m: m.group(1).replace('l', '1'), date)


re_ca = re.compile(r'ca\.([^ ])')


def parse_date(date):
    if re_date_fl.match(date):
        return {}
    date = remove_trailing_number_dot(date)
    date = re_ca.sub(lambda m: 'ca. ' + m.group(1), date)
    if date.find('-') == -1:
        for r in re_date:
            m = r.search(date)
            if m:
                return {k: fix_l_in_date(v) for k, v in m.groupdict().items()}
        return {}

    parts = date.split('-')
    i = {'birth_date': parts[0].strip()}
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


re_cent = re.compile(r'^[\dl][^-]+ cent\.$')


def pick_first_date(dates):
    # this is to handle this case:
    # 100: $aLogan, Olive (Logan), $cSikes, $dMrs., $d1839-
    # see http://archive.org/download/gettheebehindmes00logaiala/gettheebehindmes00logaiala_meta.mrc
    # or http://pharosdb.us.archive.org:9090/show-marc?record=gettheebehindmes00logaiala/gettheebehindmes00logaiala_meta.mrc:0:521

    dates = list(dates)
    if len(dates) == 1 and re_cent.match(dates[0]):
        return {'date': fix_l_in_date(dates[0])}

    for date in dates:
        result = parse_date(date)
        if result != {}:
            return result

    return {
        'date': fix_l_in_date(' '.join([remove_trailing_number_dot(d) for d in dates]))
    }


re_drop = re.compile('[?,]')


def match_with_bad_chars(a, b):
    if str(a) == str(b):
        return True
    a = normalize('NFKD', str(a)).lower()
    b = normalize('NFKD', str(b)).lower()
    if a == b:
        return True
    a = a.encode('ASCII', 'ignore')
    b = b.encode('ASCII', 'ignore')
    if a == b:
        return True

    def drop(s):
        return re_drop.sub('', s.decode() if isinstance(s, bytes) else s)

    return drop(a) == drop(b)


def accent_count(s):
    return len([c for c in norm(s) if ord(c) > 127])


def norm(s):
    return normalize('NFC', s) if isinstance(s, str) else s


def pick_best_name(names):
    names = [norm(n) for n in names]
    n1 = names[0]
    assert all(match_with_bad_chars(n1, n2) for n2 in names[1:])
    names.sort(key=lambda n: accent_count(n), reverse=True)
    assert '?' not in names[0]
    return names[0]


def pick_best_author(authors):
    n1 = authors[0]['name']
    assert all(match_with_bad_chars(n1, a['name']) for a in authors[1:])
    authors.sort(key=lambda a: accent_count(a['name']), reverse=True)
    assert '?' not in authors[0]['name']
    return authors[0]


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
        foo.setdefault(i.rstrip('.').lower() if isinstance(i, str) else i, []).append(
            (i, j)
        )
    ret = {}
    for k, v in foo.items():
        m = max(v, key=lambda x: len(x[1]))[0]
        bar = []
        for i, j in v:
            bar.extend(j)
        ret[m] = bar
    return sorted(ret.items(), key=lambda x: len(x[1]), reverse=True)


def fmt_author(a):
    if 'birth_date' in a or 'death_date' in a:
        return "{} ({}-{})".format(
            a['name'], a.get('birth_date', ''), a.get('death_date', '')
        )
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


def mk_norm(s):
    """
    Normalizes titles and strips ALL spaces and small words
    to aid with string comparisons of two titles.

    :param str s: A book title to normalize and strip.
    :rtype: str
    :return: a lowercase string with no spaces, containing the main words of the title.
    """

    m = re_brackets.match(s)
    if m:
        s = m.group(1)
    norm = merge.normalize(s).strip(' ')
    norm = norm.replace(' and ', ' ')
    if norm.startswith('the '):
        norm = norm[4:]
    elif norm.startswith('a '):
        norm = norm[2:]
    return norm.replace(' ', '')


def error_mail(msg_from, msg_to, subject, body):
    assert isinstance(msg_to, list)
    msg = 'From: {}\nTo: {}\nSubject: {}\n\n{}'.format(
        msg_from, ', '.join(msg_to), subject, body
    )

    import smtplib

    server = smtplib.SMTP('mail.archive.org')
    server.sendmail(msg_from, msg_to, msg)
    server.quit()
