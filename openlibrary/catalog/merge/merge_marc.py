import re
from names import match_name
from normalize import normalize

# fields needed for merge process:
# title_prefix, title, subtitle, isbn, publish_country, lccn, publishers, publish_date, number_of_pages, authors

re_year = re.compile('(\d{4})$')
re_amazon_title_paren = re.compile('^(.*) \([^)]+?\)$')

isbn_match = 85

def set_isbn_match(score):
    isbn_match = score

def build_titles(title):
    normalized_title = normalize(title).lower()
    titles = [ title, normalized_title ];
    if title.find(' & ') != -1:
        t = title.replace(" & ", " and ")
        titles.append(t)
        titles.append(normalize(t))
    t2 = []
    for t in titles:
        if t.lower().startswith('the '):
            t2.append(t[4:])
        elif t.lower().startswith('a '):
            t2.append(t[2:])
    titles += t2

    if re_amazon_title_paren.match(title):
        t2 = []
        for t in titles:
            m = re_amazon_title_paren.match(t)
            if m:
                t2.append(m.group(1))
                t2.append(normalize(m.group(1)))
        titles += t2

    return {
        'full_title':       title,
        'normalized_title': normalized_title,
        'titles':           titles,
        'short_title':      normalized_title[:25],
    }

def within(a, b, distance):
    return abs(a-b) <= distance

def compare_country(e1, e2):
    field = 'publish_country'
    if field not in e1 or field not in e2:
        return (field, 'value missing', 0)
    if e1[field] == e2[field]:
        return (field, 'match', 40)
    # West Berlin (wb) == Germany (gw)
    if e1[field] in ('gw ', 'wb ') and e2[field] in ('gw ', 'wb '):
        return (field, 'match', 40)
    return (field, 'mismatch', -205)

def compare_lccn(e1, e2):
    field = 'lccn'
    if field not in e1 or field not in e2:
        return (field, 'value missing', 0)
    if e1[field] == e2[field]:
        return (field, 'match', 200)
    return (field, 'mismatch', -320)

def compare_date(e1, e2):
    if 'publish_date' not in e1 or 'publish_date' not in e2:
        return ('date', 'value missing', 0)
    if e1['publish_date'] == e2['publish_date']:
        return ('date', 'exact match', 200)
    try:
        e1_pub = int(e1['publish_date'])
        e2_pub = int(e2['publish_date'])
        if within(e1_pub, e2_pub, 2):
            return ('date', '+/-2 years', -25)
        else:
            return ('date', 'mismatch', -250)
    except ValueError, TypeError:
        return ('date', 'mismatch', -250)

def compare_isbn10(e1, e2):
    if len(e1['isbn']) == 0 or len(e2['isbn']) == 0:
        return ('ISBN', 'missing', 0)
    for i in e1['isbn']:
        for j in e2['isbn']:
            if i == j:
                return ('ISBN', 'match', isbn_match)

    return ('ISBN', 'mismatch', -225)

# 450 + 200 + 85 + 200

def level1_merge(e1, e2):
    score = []
    if e1['short_title'] == e2['short_title']:
        score.append(('short-title', 'match', 450))
    else:
        score.append(('short-title', 'mismatch', 0))

    score.append(compare_lccn(e1, e2))
    score.append(compare_date(e1, e2))
    score.append(compare_isbn10(e1, e2))
    return score

def compare_author_fields(e1_authors, e2_authors):
    for i in e1_authors:
        for j in e2_authors:
            if normalize(i['db_name']) == normalize(j['db_name']):
                return True
            if normalize(i['name']).strip('.') == normalize(j['name']).strip('.'):
                return True
    return False

def compare_author_keywords(e1_authors, e2_authors):
    max_score = 0
    for i in e1_authors:
        for j in e2_authors:
            percent, ordered = keyword_match(i['name'], j['name'])
            if percent > 0.50:
                score = percent * 80
                if ordered:
                    score += 10
                if score > max_score:
                    max_score = score
    if max_score:
        return ('authors', 'keyword match', max_score)
    else:
        return ('authors', 'mismatch', -200)

def compare_authors(e1, e2):
    if 'authors' in e1 and 'authors' in e2:
        if compare_author_fields(e1['authors'], e2['authors']):
            return ('authors', 'exact match', 125)
    if 'authors' in e1 and 'contribs' in e2 and \
            compare_author_fields(e1['authors'], e2['contribs']):
        return ('authors', 'exact match', 125)
    if 'contribs' in e1 and 'authors' in e2 and \
            compare_author_fields(e1['contribs'], e2['authors']):
        return ('authors', 'exact match', 125)
    if 'authors' in e1 and 'authors' in e2:
        return compare_author_keywords(e1['authors'], e2['authors'])

    if 'authors' not in e1 and 'authors' not in e2:
        if 'contribs' in e1 and 'contribs' in e2 and \
                compare_author_fields(e1['contribs'], e2['contribs']):
            return ('authors', 'exact match', 125)
        return ('authors', 'no authors', 75)
    return ('authors', 'field missing from one record', -25)


def title_replace_amp(amazon):
    return normalize(amazon['full-title'].replace(" & ", " and ")).lower()

def substr_match(a, b):
    return a.find(b) != -1 or b.find(a) != -1

def keyword_match(in1, in2):
    s1, s2 = [i.split() for i in in1, in2]
    s1_set = set(s1)
    s2_set = set(s2)
    match = s1_set & s2_set
    if len(s1) == 0 and len(s2) == 0:
        return 0, True
    ordered = [x for x in s1 if x in match] == [x for x in s2 if x in match]
    return float(len(match)) / max(len(s1), len(s2)), ordered

def compare_title(amazon, marc):
    amazon_title = amazon['normalized_title'].lower()
    marc_title = normalize(marc['full_title']).lower()
    short = False
    if len(amazon_title) < 9 or len(marc_title) < 9:
        short = True

    if not short:
        for a in amazon['titles']:
            for m in marc['titles']:
                if a == m:
                    return ('full-title', 'exact match', 600)

        for a in amazon['titles']:
            for m in marc['titles']:
                if substr_match(a, m):
                    return ('full-title', 'containted within other title', 350)

    max_score = 0
    for a in amazon['titles']:
        for m in marc['titles']:
            percent, ordered = keyword_match(a, m)
            score = percent * 450
            if ordered:
                score += 50
            if score and score > max_score:
                max_score = score
    if max_score:
        return ('full-title', 'keyword match', max_score)
    elif short:
        return ('full-title', 'shorter than 9 characters', 0)
    else:
        return ('full-title', 'mismatch', -600)

def compare_number_of_pages(amazon, marc):
    if 'number_of_pages' not in amazon or 'number_of_pages' not in marc:
        return
    amazon_pages = amazon['number_of_pages']
    marc_pages = marc['number_of_pages']
    if amazon_pages == marc_pages:
        if amazon_pages > 10:
            return ('pagination', 'match exactly and > 10', 100)
        else:
            return ('pagination', 'match exactly and < 10', 50)
    elif within(amazon_pages, marc_pages, 10):
        if amazon_pages > 10 and marc_pages > 10:
            return ('pagination', 'match within 10 and both are > 10', 50)
        else:
            return ('pagination', 'match within 10 and either are < 10', 20)
    else:
        return ('pagination', 'non-match (by more than 10)', -225)

def short_part_publisher_match(p1, p2):
    pub1 = p1.split()
    pub2 = p2.split()
    if len(pub1) == 1 or len(pub2) == 1:
        return False
    for i, j in zip(pub1, pub2):
        if not substr_match(i, j):
            return False
    return True

def compare_publisher(e1, e2):
    if 'publishers' in e1 and 'publishers' in e2:
        for e1_pub in e1['publishers']:
            e1_norm = normalize(e1_pub)
            for e2_pub in e2['publishers']:
                e2_norm = normalize(e2_pub)
                if e1_norm == e2_norm:
                    return ('publisher', 'match', 100)
                elif substr_match(e1_norm, e2_norm):
                    return ('publisher', 'occur within the other', 100)
                elif substr_match(e1_norm.replace(' ', ''), e2_norm.replace(' ', '')):
                    return ('publisher', 'occur within the other', 100)
                elif short_part_publisher_match(e1_norm, e2_norm):
                    return ('publisher', 'match', 100)
        return ('publisher', 'mismatch', -25)

    if 'publishers' not in e1 or 'publishers' not in e2:
        return ('publisher', 'either missing', 0)

def level2_merge(e1, e2):
    score = []
    score.append(compare_date(e1, e2))
    score.append(compare_country(e1, e2))
    score.append(compare_isbn10(e1, e2))
    score.append(compare_title(e1, e2))
    score.append(compare_lccn(e1, e2))
    page_score = compare_number_of_pages(e1, e2)
    if page_score:
        score.append(page_score)

    score.append(compare_publisher(e1, e2))
    score.append(compare_authors(e1, e2))

    return score

def build_marc(edition):
    marc = build_titles(edition['full_title'])
    if 'isbn' in edition:
        marc['isbn'] = edition['isbn']
    else:
        marc['isbn'] = []
    if 'publish_country' in edition \
            and edition['publish_country'] not in ('   ', '|||'):
        marc['publish_country'] = edition['publish_country']
    for f in 'lccn', 'publishers', 'publish_date', 'number_of_pages', 'authors', 'contribs':
        if f in edition:
            marc[f] = edition[f]
    return marc

def attempt_merge(e1, e2, threshold, debug = False):
    l1 = level1_merge(e1, e2)
    total = sum(i[2] for i in l1)
    if debug:
        print total, l1
    if total >= threshold:
        return True
    l2 = level2_merge(e1, e2)
    total = sum(i[2] for i in l2)
    if debug:
        print total, l2
    return total >= threshold

def test_merge():
    bpl = {'authors': [{'birth_date': u'1897',
                      'db_name': u'Green, Constance McLaughlin 1897-',
                      'entity_type': 'person',
                      'name': u'Green, Constance McLaughlin',
                      'personal_name': u'Green, Constance McLaughlin'}],
         'full_title': u'Eli Whitney and the birth of American technology',
         'isbn': [u'188674632X'],
         'normalized_title': u'eli whitney and the birth of american technology',
         'number_of_pages': 215,
         'publish_date': '1956',
         'publishers': [u'HarperCollins', u'[distributed by Talman Pub.]'],
         'short_title': u'eli whitney and the birth',
         'source_record_loc': 'bpl101.mrc:0:1226',
         'titles': [u'Eli Whitney and the birth of American technology',
                    u'eli whitney and the birth of american technology']}
    lc = {'authors': [{'birth_date': u'1897',
                     'db_name': u'Green, Constance McLaughlin 1897-',
                     'entity_type': 'person',
                     'name': u'Green, Constance McLaughlin',
                     'personal_name': u'Green, Constance McLaughlin'}],
        'full_title': u'Eli Whitney and the birth of American technology.',
        'isbn': [],
        'normalized_title': u'eli whitney and the birth of american technology',
        'number_of_pages': 215,
        'publish_date': '1956',
        'publishers': ['Little, Brown'],
        'short_title': u'eli whitney and the birth',
        'source_record_loc': 'marc_records_scriblio_net/part04.dat:119539872:591',
        'titles': [u'Eli Whitney and the birth of American technology.',
                   u'eli whitney and the birth of american technology']}

    assert compare_authors(bpl, lc) == ('authors', 'exact match', 125)
    threshold = 735
    assert attempt_merge(bpl, lc, threshold)

def test_author_contrib():
    rec1 = {'authors': [{'db_name': u'Bruner, Jerome S.', 'name': u'Bruner, Jerome S.'}],
    'full_title': u'Contemporary approaches to cognition a symposium held at the University of Colorado.',
    'number_of_pages': 210,
    'publish_country': 'xxu',
    'publish_date': '1957',
    'publishers': [u'Harvard U.P']}

    rec2 = {'authors': [{'db_name': u'University of Colorado (Boulder campus). Dept. of Psychology.',
                'name': u'University of Colorado (Boulder campus). Dept. of Psychology.'}],
    'contribs': [{'db_name': u'Bruner, Jerome S.', 'name': u'Bruner, Jerome S.'}],
    'full_title': u'Contemporary approaches to cognition a symposium held at the University of Colorado',
    'lccn': ['57012963'],
    'number_of_pages': 210,
    'publish_country': 'mau',
    'publish_date': '1957',
    'publishers': [u'Harvard University Press']}

    e1 = build_marc(rec1)
    e2 = build_marc(rec2)

    assert compare_authors(e1, e2) == ('authors', 'exact match', 125)
    threshold = 875
    assert attempt_merge(e1, e2, threshold)

test_author_contrib()
