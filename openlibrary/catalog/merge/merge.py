import re
import warnings

from openlibrary.catalog.merge.names import match_name
from openlibrary.catalog.merge.normalize import normalize


re_amazon_title_paren = re.compile('^(.*) \([^)]+?\)$')
re_and_of_space = re.compile(' and | of | ')

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

def compare_date(e1, e2):
    if 'publish_date' not in e1 or 'publish_date' not in e2:
        return ('date', 'value missing', 0)
    if e1['publish_date'] == e2['publish_date']:
        return ('date', 'exact match', 200)
    try:
        e1_pub = int(e1['publish_date'])
        e2_pub = int(e2['publish_date'])
        if within(e1_pub, e2_pub, 1):
            return ('date', 'within 1 year', 100)
        elif within(e1_pub, e2_pub, 2):
            return ('date', '+/-2 years', -25)
        else:
            return ('date', 'mismatch', -250)
    except ValueError as TypeError:
        return ('date', 'mismatch', -250)


def compare_isbn10(e1, e2):
    warnings.warn('Deprecated, use openlibrary.catalog.merge.merge_marc.compare_isbn10() instead.', DeprecationWarning)

    if len(e1['isbn']) == 0 or len(e2['isbn']) == 0:
        return ('ISBN', 'missing', 0)
    for i in e1['isbn']:
        for j in e2['isbn']:
            if i == j:
                return ('ISBN', 'match', isbn_match)

    return ('ISBN', 'mismatch', -225)

def level1_merge(e1, e2):
    warnings.warn('Deprecated, use openlibrary.catalog.merge.merge_marc.level1_merge() instead.', DeprecationWarning)

    score = []
    if e1['short_title'] == e2['short_title']:
        score.append(('short-title', 'match', 450))
    else:
        score.append(('short-title', 'mismatch', 0))

    score.append(compare_date(e1, e2))
    score.append(compare_isbn10(e1, e2))
    return score

def compare_authors(amazon, marc):
    warnings.warn('Deprecated, use openlibrary.catalog.merge.merge_marc.compare_authors() instead.', DeprecationWarning)

    if len(amazon['authors']) == 0 and 'authors' not in marc:
        return ('main', 'no authors', 75)
    if len(amazon['authors']) == 0:
        return ('main', 'field missing from one record', -25)

    for name in amazon['authors']:
        if 'authors' in marc and match_name(name, marc['authors'][0]['name']):
            return ('main', 'exact match', 125)
        if 'by_statement' in marc and marc['by_statement'].find(name) != -1:
            return ('main', 'exact match', 125)
    if 'authors' not in marc:
        return ('main', 'field missing from one record', -25)

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
        return ('main', 'keyword match', max_score)
    else:
        return ('main', 'mismatch', -200)

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
                    return ('full-title', 'exact match', 600)
                if strip_and_compare(a, m):
                    return ('full-title', 'exact match', 600)

        for a in amazon['titles']:
            for m in marc['titles']:
                if substr_match(a.lower(), m.lower()):
                    return ('full-title', 'contained within other title', 350)

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

def compare_publisher(amazon, marc):
    if 'publisher' in amazon and 'publishers' in marc:
        amazon_pub = amazon['publisher']
        norm_amazon = normalize(amazon_pub)
        for marc_pub in marc['publishers']:
            norm_marc = normalize(marc_pub)
            if norm_amazon == norm_marc:
                return ('publisher', 'match', 100)
            elif substr_match(norm_amazon, norm_marc):
                return ('publisher', 'occur within the other', 100)
            elif substr_match(norm_amazon.replace(' ', ''), norm_marc.replace(' ', '')):
                return ('publisher', 'occur within the other', 100)
            elif short_part_publisher_match(norm_amazon, norm_marc):
                return ('publisher', 'match', 100)
        return ('publisher', 'mismatch', -25)

    if 'publisher' not in amazon or 'publishers' not in marc:
        return ('publisher', 'either missing', 0)

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

def attempt_merge(amazon, marc, threshold):
    warnings.warn('Deprecated, use openlibrary.catalog.merge.merge_marc.attempt_merge() instead.', DeprecationWarning)

    l1 = level1_merge(amazon, marc)
    total = sum(i[2] for i in l1)
    if total >= threshold:
        return True
    l2 = level2_merge(amazon, marc)
    total = sum(i[2] for i in l2)
    return total >= threshold
