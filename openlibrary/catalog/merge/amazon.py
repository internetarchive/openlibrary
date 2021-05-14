from __future__ import print_function
import re
import warnings

from openlibrary.catalog.merge.names import match_name
from openlibrary.catalog.merge.normalize import normalize

re_year = re.compile(r'(\d{4})$')
re_amazon_title_paren = re.compile(r'^(.*) \([^)]+?\)$')
re_and_of_space = re.compile(' and | of | ')

isbn_match = 85


def set_isbn_match(score):
    isbn_match = score


def amazon_year(date):
    m = re_year.search(date)
    assert m
    year = m.group(1)
    return year


def build_amazon(edition, authors):
    amazon = build_titles(full_title(edition))
    amazon['isbn'] = edition['isbn_10']
    if 'publish_date' in edition:
        amazon['publish_date'] = amazon_year(edition['publish_date'])
    if authors:
        amazon['authors'] = authors
    else:
        amazon['authors'] = []
    if 'number_of_pages' in edition:
        amazon['number_of_pages'] = edition['number_of_pages']
    if 'publishers' in edition:
        amazon['publishers'] = edition['publishers']
    return amazon


def build_titles(title):
    warnings.warn('Deprecated, use openlibrary.catalog.merge.merge_marc.build_titles() instead.', DeprecationWarning)

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

def compare_date(e1, e2):
    if 'publish_date' not in e1 or 'publish_date' not in e2:
        return ('publish_date', 'value missing', 0)
    if e1['publish_date'] == e2['publish_date']:
        return ('publish_date', 'exact match', 200)
    try:
        e1_pub = int(e1['publish_date'])
        e2_pub = int(e2['publish_date'])
        if within(e1_pub, e2_pub, 1):
            return ('publish_date', 'within 1 year', 100)
        elif within(e1_pub, e2_pub, 2):
            return ('publish_date', '+/-2 years', -25)
        else:
            return ('publish_date', 'mismatch', -250)
    except ValueError as TypeError:
        return ('publish_date', 'mismatch', -250)

def compare_isbn10(e1, e2):
    warnings.warn('Deprecated, use openlibrary.catalog.merge.merge_marc.compare_isbn10() instead.', DeprecationWarning)

    if len(e1['isbn']) == 0 or len(e2['isbn']) == 0:
        return ('isbn', 'missing', 0)
    for i in e1['isbn']:
        for j in e2['isbn']:
            if i == j:
                return ('isbn', 'match', isbn_match)
    return ('ISBN', 'mismatch', -225)

def level1_merge(e1, e2):
    warnings.warn('Deprecated, use openlibrary.catalog.merge.merge_marc.level1_merge() instead.', DeprecationWarning)

    score = []
    if e1['short_title'] == e2['short_title']:
        score.append(('short_title', 'match', 450))
    else:
        score.append(('short_title', 'mismatch', 0))

    score.append(compare_date(e1, e2))
    score.append(compare_isbn10(e1, e2))
    return score

def compare_authors(amazon, marc):
    warnings.warn('Deprecated, use openlibrary.catalog.merge.merge_marc.compare_authors() instead.', DeprecationWarning)

    if len(amazon['authors']) == 0 and 'authors' not in marc:
        return ('authors', 'no authors', 75)
    if len(amazon['authors']) == 0:
        return ('authors', 'field missing from one record', -25)

    for name in amazon['authors']:
        if 'authors' in marc and match_name(name, marc['authors'][0]['name']):
            return ('authors', 'exact match', 125)
        if 'by_statement' in marc and marc['by_statement'].find(name) != -1:
            return ('authors', 'exact match', 125)
    if 'authors' not in marc:
        return ('authors', 'field missing from one record', -25)

    max_score = 0
    for a in amazon['authors']:
        percent, ordered = keyword_match(a[0], marc['authors'][0]['name'])
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

def title_replace_amp(amazon):
    return normalize(amazon['full-title'].replace(" & ", " and ")).lower()

def substr_match(a, b):
    return a.find(b) != -1 or b.find(a) != -1

def keyword_match(in1, in2):
    s1, s2 = [i.split() for i in (in1, in2)]
    s1_set = set(s1)
    s2_set = set(s2)
    match = s1_set & s2_set
    if len(s1) == 0 and len(s2) == 0:
        return 0, True
    ordered = [x for x in s1 if x in match] == [x for x in s2 if x in match]
    return float(len(match)) / max(len(s1), len(s2)), ordered

def strip_and_compare(t1, t2):
    t1 = re_and_of_space.sub('', t1).lower()
    t2 = re_and_of_space.sub('', t2).lower()
    return t1 == t2

def compare_title(amazon, marc):
    amazon_title = amazon['normalized_title'].lower()
    marc_title = normalize(marc['full_title']).lower()
    short = False
    if len(amazon_title) < 9 or len(marc_title) < 9:
        short = True

    if not short:
        for a in amazon['titles']:
            for m in marc['titles']:
                if a.lower() == m.lower():
                    return ('full_title', 'exact match', 600)
                if strip_and_compare(a, m):
                    return ('full_title', 'exact match', 600)

        for a in amazon['titles']:
            for m in marc['titles']:
                if substr_match(a.lower(), m.lower()):
                    return ('full_title', 'contained within other title', 350)

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
        return ('full_title', 'keyword match', max_score)
    elif short:
        return ('full_title', 'shorter than 9 characters', 0)
    else:
        return ('full_title', 'mismatch', -600)

def compare_number_of_pages(amazon, marc):
    if 'number_of_pages' not in amazon or 'number_of_pages' not in marc:
        return
    amazon_pages = amazon['number_of_pages']
    marc_pages = marc['number_of_pages']
    if amazon_pages == marc_pages:
        if amazon_pages > 10:
            return ('number_of_pages', 'match exactly and > 10', 100)
        else:
            return ('number_of_pages', 'match exactly and < 10', 50)
    elif within(amazon_pages, marc_pages, 10):
        if amazon_pages > 10 and marc_pages > 10:
            return ('number_of_pages', 'match within 10 and both are > 10', 50)
        else:
            return ('number_of_pages', 'match within 10 and either are < 10', 20)
    else:
        return ('number_of_pages', 'non-match (by more than 10)', -225)

def short_part_publisher_match(p1, p2):
    pub1 = p1.split()
    pub2 = p2.split()
    if len(pub1) == 1 or len(pub2) == 1:
        return False
    for i, j in zip(pub1, pub2):
        if not substr_match(i, j):
            return False
    return True

re_press = re.compile(' press$')

def compare_publisher(amazon, marc):
    if 'publishers' not in amazon or 'publishers' not in marc:
        return ('publishers', 'either missing', 0)

    assert 'publishers' in amazon and 'publishers' in marc
    for amazon_pub in amazon['publishers']:
        norm_amazon = normalize(amazon_pub)
        for marc_pub in marc['publishers']:
            norm_marc = normalize(marc_pub)
            if norm_amazon == norm_marc:
                return ('publishers', 'match', 100)
#            if re_press.sub('', norm_amazon) == re_press.sub('', norm_marc):
#                return ('publishers', 'match', 100)
            if substr_match(norm_amazon, norm_marc):
                return ('publishers', 'occur within the other', 100)
            if substr_match(norm_amazon.replace(' ', ''), norm_marc.replace(' ', '')):
                return ('publishers', 'occur within the other', 100)
            if short_part_publisher_match(norm_amazon, norm_marc):
                return ('publishers', 'match', 100)
    return ('publishers', 'mismatch', -25)

def level2_merge(amazon, marc):
    warnings.warn('Deprecated, use openlibrary.catalog.merge.merge_marc.level2_merge() instead.', DeprecationWarning)
    score = []
    score.append(compare_date(amazon, marc))
    score.append(compare_isbn10(amazon, marc))
    score.append(compare_title(amazon, marc))
    page_score = compare_number_of_pages(amazon, marc)
    if page_score:
        score.append(page_score)

    score.append(compare_publisher(amazon, marc))
    score.append(compare_authors(amazon, marc))

    return score

def full_title(edition):
    title = edition['title']
    if 'subtitle' in edition:
        title += ' ' + edition['subtitle']
    return title


def attempt_merge(amazon, marc, threshold, debug = False):
    warnings.warn('Deprecated, use openlibrary.catalog.merge.merge_marc.attempt_merge() instead.', DeprecationWarning)
    l1 = level1_merge(amazon, marc)
    total = sum(i[2] for i in l1)
    if debug:
        print(total, l1)
    if total >= threshold:
        return True
    l2 = level2_merge(amazon, marc)
    total = sum(i[2] for i in l2)
    if debug:
        print(total, l2)
    return total >= threshold
