import re
import unicodedata

# fields needed for matching:
# title, subtitle, isbn, publish_country, lccn, publishers, publish_date, number_of_pages, authors

re_amazon_title_paren = re.compile(r'^(.*) \([^)]+?\)$')
re_brackets = re.compile(r'^(.+)\[.*?\]$')
re_whitespace_and_punct = re.compile(r'[-\s,;:.]+')

ISBN_MATCH = 85
THRESHOLD = 875


def editions_match(rec: dict, existing) -> bool:
    """
    Converts the existing edition into a comparable dict and performs a
    thresholded comparison to decide whether they are the same.
    Used by add_book.load() -> add_book.find_match() to check whether two
    editions match.

    :param dict rec: Import record candidate
    :param Thing existing: Edition object to be tested against candidate
    :rtype: bool
    :return: Whether candidate is sufficiently the same as the 'existing' edition
    """
    thing_type = existing.type.key
    if thing_type == '/type/delete':
        return False
    assert thing_type == '/type/edition'
    rec2 = {}
    for f in (
        'title',
        'subtitle',
        'isbn',
        'isbn_10',
        'isbn_13',
        'lccn',
        'publish_country',
        'publishers',
        'publish_date',
    ):
        if existing.get(f):
            rec2[f] = existing[f]
    rec2['authors'] = []
    # Transfer authors as Dicts str: str
    for a in existing.get_authors():
        author = {'name': a['name']}
        if birth := a.get('birth_date'):
            author['birth_date'] = birth
        if death := a.get('death_date'):
            author['death_date'] = death
        rec2['authors'].append(author)
    return threshold_match(rec, rec2, THRESHOLD)


def normalize(s: str) -> str:
    """
    Normalizes a title for matching purposes, not display,
    by lowercasing, unicode -> NFC,
    stripping extra whitespace and punctuation, and replacing ampersands.
    """

    s = unicodedata.normalize('NFC', s)
    s = s.replace(' & ', ' and ')
    s = re_whitespace_and_punct.sub(' ', s.lower()).strip()
    return s


def mk_norm(s: str) -> str:
    """
    Normalizes titles and strips ALL spaces and small words
    to aid with string comparisons of two titles.
    Used in comparing Work titles.

    :param str s: A book title to normalize and strip.
    :return: a lowercase string with no spaces, containing the main words of the title.
    """
    if m := re_brackets.match(s):
        s = m.group(1)
    norm = normalize(s).replace(' and ', '')
    return strip_articles(norm).replace(' ', '')


def strip_articles(s: str) -> str:
    """
    Strip articles for matching purposes.
    TODO: Expand using
    https://web.archive.org/web/20230320141510/https://www.loc.gov/marc/bibliographic/bdapndxf.html
    or something sensible.
    """
    if s.lower().startswith('the '):
        s = s[4:]
    elif s.lower().startswith('a '):
        s = s[2:]
    return s


def add_db_name(rec: dict) -> None:
    """
    db_name = Author name followed by dates.
    adds 'db_name' in place for each author.
    """
    if 'authors' not in rec:
        return

    for a in rec['authors'] or []:
        date = None
        if 'date' in a:
            assert 'birth_date' not in a
            assert 'death_date' not in a
            date = a['date']
        elif 'birth_date' in a or 'death_date' in a:
            date = a.get('birth_date', '') + '-' + a.get('death_date', '')
        a['db_name'] = ' '.join([a['name'], date]) if date else a['name']


def expand_record(rec: dict) -> dict[str, str | list[str]]:
    """
    Returns an expanded representation of an edition dict,
    usable for accurate comparisons between existing and new
    records.

    :param dict rec: Import edition representation
    :return: An expanded version of an edition dict
        more titles, normalized + short
        all isbns in "isbn": []
        authors have db_name (name with dates)
    """
    rec['full_title'] = rec['title']
    if subtitle := rec.get('subtitle'):
        rec['full_title'] += ' ' + subtitle
    expanded_rec = build_titles(rec['full_title'])
    expanded_rec['isbn'] = []
    for f in 'isbn', 'isbn_10', 'isbn_13':
        expanded_rec['isbn'].extend(rec.get(f, []))
    if 'publish_country' in rec and rec['publish_country'] not in (
        '   ',
        '|||',
    ):
        expanded_rec['publish_country'] = rec['publish_country']
    for f in (
        'lccn',
        'publishers',
        'publish_date',
        'number_of_pages',
        'authors',
        'contribs',
    ):
        if f in rec:
            expanded_rec[f] = rec[f]
    add_db_name(expanded_rec)
    return expanded_rec


def build_titles(title: str):
    """
    Uses a full title to create normalized and short title versions.
    Used for expanding a set of title variants for matching,
    not for storing on records or display.

    :param str title: Full title of an edition
    :rtype: dict
    :return: An expanded set of title variations
    """
    normalized_title = normalize(title)
    titles = [  # TODO: how different and helpful are these titles variants?
        title,
        normalized_title,
        strip_articles(normalized_title),
    ]
    if m := re_amazon_title_paren.match(normalized_title):
        titles.append(m.group(1))
        titles.append(strip_articles(m.group(1)))

    return {
        'full_title': title,
        'normalized_title': normalized_title,
        'titles': list(set(titles)),
        'short_title': normalized_title[:25],
    }


def within(a, b, distance):
    return abs(a - b) <= distance


def compare_country(e1: dict, e2: dict):
    field = 'publish_country'
    if field not in e1 or field not in e2:
        return (field, 'value missing', 0)
    if e1[field] == e2[field]:
        return (field, 'match', 40)
    # West Berlin (wb) == Germany (gw)
    if e1[field] in ('gw ', 'wb ') and e2[field] in ('gw ', 'wb '):
        return (field, 'match', 40)
    return (field, 'mismatch', -205)


def compare_lccn(e1: dict, e2: dict):
    field = 'lccn'
    if field not in e1 or field not in e2:
        return (field, 'value missing', 0)
    if e1[field] == e2[field]:
        return (field, 'match', 200)
    return (field, 'mismatch', -320)


def compare_date(e1: dict, e2: dict):
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
    except ValueError as TypeError:
        return ('date', 'mismatch', -250)


def compare_isbn(e1: dict, e2: dict):
    if len(e1['isbn']) == 0 or len(e2['isbn']) == 0:
        return ('ISBN', 'missing', 0)
    for i in e1['isbn']:
        for j in e2['isbn']:
            if i == j:
                return ('ISBN', 'match', ISBN_MATCH)
    return ('ISBN', 'mismatch', -225)


# 450 + 200 + 85 + 200


def level1_match(e1: dict, e2: dict):
    """
    :param dict e1: Expanded Edition, output of expand_record()
    :param dict e2: Expanded Edition, output of expand_record()
    :rtype: list
    :return: a list of tuples (field/category, result str, score int)
    """
    score = []
    if e1['short_title'] == e2['short_title']:
        score.append(('short-title', 'match', 450))
    else:
        score.append(('short-title', 'mismatch', 0))

    score.append(compare_lccn(e1, e2))
    score.append(compare_date(e1, e2))
    score.append(compare_isbn(e1, e2))
    return score


def level2_match(e1: dict, e2: dict):
    """
    :param dict e1: Expanded Edition, output of expand_record()
    :param dict e2: Expanded Edition, output of expand_record()
    :rtype: list
    :return: a list of tuples (field/category, result str, score int)
    """
    score = []
    score.append(compare_date(e1, e2))
    score.append(compare_country(e1, e2))
    score.append(compare_isbn(e1, e2))
    score.append(compare_title(e1, e2))
    score.append(compare_lccn(e1, e2))
    if page_score := compare_number_of_pages(e1, e2):
        score.append(page_score)
    score.append(compare_publisher(e1, e2))
    score.append(compare_authors(e1, e2))
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
                max_score = max(score, max_score)
    if max_score:
        return ('authors', 'keyword match', max_score)
    else:
        return ('authors', 'mismatch', -200)


def compare_authors(e1: dict, e2: dict):
    """
    Compares the authors of two edition representations and
    returns a evaluation and score.

    :param dict e1: Expanded Edition, output of expand_record()
    :param dict e2: Expanded Edition, output of expand_record()
    :rtype: tuple
    :return: str?, message, score
    """
    if 'authors' in e1 and 'authors' in e2:  # noqa: SIM102
        if compare_author_fields(e1['authors'], e2['authors']):
            return ('authors', 'exact match', 125)

    if 'authors' in e1 and 'contribs' in e2:  # noqa: SIM102
        if compare_author_fields(e1['authors'], e2['contribs']):
            return ('authors', 'exact match', 125)

    if 'contribs' in e1 and 'authors' in e2:  # noqa: SIM102
        if compare_author_fields(e1['contribs'], e2['authors']):
            return ('authors', 'exact match', 125)

    if 'authors' in e1 and 'authors' in e2:
        return compare_author_keywords(e1['authors'], e2['authors'])

    if 'authors' not in e1 and 'authors' not in e2:
        if (
            'contribs' in e1
            and 'contribs' in e2
            and compare_author_fields(e1['contribs'], e2['contribs'])
        ):
            return ('authors', 'exact match', 125)
        return ('authors', 'no authors', 75)
    return ('authors', 'field missing from one record', -25)


def title_replace_amp(amazon):
    return normalize(amazon['full-title'].replace(" & ", " and ")).lower()


def substr_match(a: str, b: str):
    return a.find(b) != -1 or b.find(a) != -1


def keyword_match(in1, in2):
    s1, s2 = (i.split() for i in (in1, in2))
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
    return all(substr_match(i, j) for i, j in zip(pub1, pub2))


def compare_publisher(e1: dict, e2: dict):
    if 'publishers' in e1 and 'publishers' in e2:
        for e1_pub in e1['publishers']:
            e1_norm = normalize(e1_pub)
            for e2_pub in e2['publishers']:
                e2_norm = normalize(e2_pub)
                if e1_norm == e2_norm:
                    return ('publisher', 'match', 100)
                elif substr_match(e1_norm, e2_norm) or substr_match(
                    e1_norm.replace(' ', ''), e2_norm.replace(' ', '')
                ):
                    return ('publisher', 'occur within the other', 100)
                elif short_part_publisher_match(e1_norm, e2_norm):
                    return ('publisher', 'match', 100)
        return ('publisher', 'mismatch', -51)

    if 'publishers' not in e1 or 'publishers' not in e2:
        return ('publisher', 'either missing', 0)


def threshold_match(
    rec1: dict, rec2: dict, threshold: int, debug: bool = False
) -> bool:
    """
    Determines (according to a threshold) whether two edition representations are
    sufficiently the same. Used when importing new books.

    :param dict e1: dict representing an import schema edition
    :param dict e2: dict representing an import schema edition
    :param int threshold: each field match or difference adds or subtracts a score. Example: 875 for standard edition matching
    :rtype: bool
    :return: Whether two editions have sufficient fields in common to be considered the same
    """
    e1 = expand_record(rec1)
    e2 = expand_record(rec2)
    level1 = level1_match(e1, e2)
    total = sum(i[2] for i in level1)
    if debug:
        print(f"E1: {e1}\nE2: {e2}", flush=True)
        print(f"TOTAL 1 = {total} : {level1}", flush=True)
    if total >= threshold:
        return True
    level2 = level2_match(e1, e2)
    total = sum(i[2] for i in level2)
    if debug:
        print(f"TOTAL 2 = {total} : {level2}", flush=True)
    return total >= threshold
