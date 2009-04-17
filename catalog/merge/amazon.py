import re
from names import match_name
from normalize import normalize

re_year = re.compile('(\d{4})$')
re_amazon_title_paren = re.compile('^(.*) \([^)]+?\)$')
re_and_of_space = re.compile(' and | of | ')

isbn_match = 85

def set_isbn_match(score):
    isbn_match = score

def amazon_year(date):
    m = re_year.search(date)
    try:
        assert m
        year = m.group(1)
    except:
        print date
        raise
    return year

def build_amazon(edition, authors):
    amazon = build_titles(full_title(edition))

    amazon['isbn'] = edition['isbn_10']
    if 'publish_date' in edition:
        try:
            amazon['publish_date'] = amazon_year(edition['publish_date'])
        except:
            print edition['isbn_10'], edition['publish_date']
            raise
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
    except ValueError, TypeError:
        return ('publish_date', 'mismatch', -250)

def compare_isbn10(e1, e2):
    if len(e1['isbn']) == 0 or len(e2['isbn']) == 0:
        return ('isbn', 'missing', 0)
    for i in e1['isbn']:
        for j in e2['isbn']:
            if i == j:
                return ('isbn', 'match', isbn_match)

    return ('ISBN', 'mismatch', -225)

def level1_merge(e1, e2):
    score = []
    if e1['short_title'] == e2['short_title']:
        score.append(('short_title', 'match', 450))
    else:
        score.append(('short_title', 'mismatch', 0))

    score.append(compare_date(e1, e2))
    score.append(compare_isbn10(e1, e2))
    return score

def compare_authors(amazon, marc):
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
    s1, s2 = [i.split() for i in in1, in2]
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

def test_full_title():
    assert full_title({ 'title': "Hamlet"}) == "Hamlet"
    edition = {
        'title': 'Flatland',
        'subtitle': 'A Romance of Many Dimensions',
    }
    assert full_title(edition) == "Flatland A Romance of Many Dimensions"

def test_merge_titles():
    marc = {
        'title_with_subtitles': 'Spytime : the undoing of James Jesus Angleton : a novel',
        'title': 'Spytime',
        'full_title': 'Spytime : the undoing of James Jesus Angleton : a novel',
    }
    amazon = {
        'subtitle': 'The Undoing oF James Jesus Angleton',
        'title': 'Spytime',
    }

    amazon = build_titles(unicode(full_title(amazon)))
    marc = build_titles(marc['title_with_subtitles'])
    assert amazon['short_title'] == marc['short_title']
    assert compare_title(amazon, marc) == ('full-title', 'containted within other title', 350)

def test_merge_titles2():
    amazon = {'title': u'Sea Birds Britain Ireland'}
    marc = {
        'title_with_subtitles': u'seabirds of Britain and Ireland',
        'title': u'seabirds of Britain and Ireland', 
        'full_title': u'The seabirds of Britain and Ireland',
    }
    amazon = build_titles(unicode(full_title(amazon)))
    marc = build_titles(marc['title_with_subtitles'])
    assert compare_title(amazon, marc) == ('full-title', 'exact match', 600)

def attempt_merge(amazon, marc, threshold, debug = False):
    l1 = level1_merge(amazon, marc)
    total = sum(i[2] for i in l1)
    if debug:
        print total, l1
    if total >= threshold:
        return True
    l2 = level2_merge(amazon, marc)
    total = sum(i[2] for i in l2)
    if debug:
        print total, l2
    return total >= threshold

def test_merge():
    amazon = {'publishers': [u'Collins'], 'isbn_10': ['0002167360'], 'number_of_pages': 120, 'short_title': u'souvenirs', 'normalized_title': u'souvenirs', 'full_title': u'Souvenirs', 'titles': [u'Souvenirs', u'souvenirs'], 'publish_date': u'1975', 'authors': [(u'David Hamilton', u'Photographer')]}
    marc = {'publisher': [u'Collins'], 'isbn_10': [u'0002167360'], 'short_title': u'souvenirs', 'normalized_title': u'souvenirs', 'full_title': u'Souvenirs', 'titles': [u'Souvenirs', u'souvenirs'], 'publish_date': '1978', 'authors': [{'birth_date': u'1933', 'db_name': u'Hamilton, David 1933-', 'entity_type': 'person', 'name': u'Hamilton, David', 'personal_name': u'Hamilton, David'}], 'source_record_loc': 'marc_records_scriblio_net/part11.dat:155728070:617', 'number_of_pages': 120}

    threshold = 735
    assert attempt_merge(amazon, marc, threshold)

def test_merge2():
    amazon = {'publishers': [u'Collins'], 'isbn_10': ['0002167530'], 'number_of_pages': 287, 'short_title': u'sea birds britain ireland', 'normalized_title': u'sea birds britain ireland', 'full_title': u'Sea Birds Britain Ireland', 'titles': [u'Sea Birds Britain Ireland', u'sea birds britain ireland'], 'publish_date': u'1975', 'authors': [(u'Stanley Cramp', u'Author')]}
    marc = {'publisher': [u'Collins'], 'isbn_10': [u'0002167530'], 'short_title': u'seabirds of britain and i', 'normalized_title': u'seabirds of britain and ireland', 'full_title': u'seabirds of Britain and Ireland', 'titles': [u'seabirds of Britain and Ireland', u'seabirds of britain and ireland'], 'publish_date': '1974', 'authors': [{'db_name': u'Cramp, Stanley.', 'entity_type': 'person', 'name': u'Cramp, Stanley.', 'personal_name': u'Cramp, Stanley.'}], 'source_record_loc': 'marc_records_scriblio_net/part08.dat:61449973:855'}

    threshold = 735
    #assert attempt_merge(amazon, marc, threshold)

def test_merge3():
    amazon = {'publishers': [u'Intl Specialized Book Service Inc'], 'isbn_10': ['0002169770'], 'number_of_pages': 207, 'short_title': u'women of the north', 'normalized_title': u'women of the north', 'full_title': u'Women of the North', 'titles': [u'Women of the North', u'women of the north'], 'publish_date': u'1985', 'authors': [(u'Jane Wordsworth', u'Author')]}
    marc = {'publisher': [u'Collins', u'Exclusive distributor ISBS'], 'isbn_10': [u'0002169770'], 'short_title': u'women of the north', 'normalized_title': u'women of the north', 'full_title': u'Women of the North', 'titles': [u'Women of the North', u'women of the north'], 'publish_date': '1981', 'number_of_pages': 207, 'authors': [{'db_name': u'Wordsworth, Jane.', 'entity_type': 'person', 'name': u'Wordsworth, Jane.', 'personal_name': u'Wordsworth, Jane.'}], 'source_record_loc': 'marc_records_scriblio_net/part17.dat:110989084:798'}

    threshold = 735
#    assert attempt_merge(amazon, marc, threshold)

def test_merge4():
    amazon = {'publishers': [u'HarperCollins Publishers Ltd'], 'isbn_10': ['0002173433'], 'number_of_pages': 128, 'short_title': u'd day to victory', 'normalized_title': u'd day to victory', 'full_title': u'D-Day to Victory', 'titles': [u'D-Day to Victory', u'd day to victory'], 'publish_date': u'1984', 'authors': [(u'Wynfod Vaughan-Thomas', u'Editor, Introduction')]}
    marc = {'publisher': [u'Collins'], 'isbn_10': [u'0002173433'], 'short_title': u'great front pages  d day ', 'normalized_title': u'great front pages  d day to victory 1944 1945', 'full_title': u'Great front pages : D-Day to victory 1944-1945', 'titles': [u'Great front pages : D-Day to victory 1944-1945', u'great front pages  dday to victory 1944 1945'], 'publish_date': '1984', 'number_of_pages': 128, 'by_statement': 'introduced by Wynford Vaughan-Thomas.', 'source_record_loc': 'marc_records_scriblio_net/part17.dat:102360356:983'}

    threshold = 735
    assert attempt_merge(amazon, marc, threshold)

def test_merge5():
    amazon = {'publishers': [u'HarperCollins Publishers (Australia) Pty Ltd'], 'isbn_10': ['0002174049'], 'number_of_pages': 120, 'short_title': u'netherlandish and german ', 'normalized_title': u'netherlandish and german paintings national gallery schools of painting', 'full_title': u'Netherlandish and German Paintings (National Gallery Schools of Painting)', 'titles': [u'Netherlandish and German Paintings (National Gallery Schools of Painting)', u'netherlandish and german paintings national gallery schools of painting', u'Netherlandish and German Paintings', u'netherlandish and german paintings'], 'publish_date': u'1985', 'authors': [(u'Alistair Smith', u'Author')]}
    marc = {'publisher': [u'National Gallery in association with W. Collins'], 'isbn_10': [u'0002174049'], 'short_title': u'early netherlandish and g', 'normalized_title': u'early netherlandish and german paintings', 'full_title': u'Early Netherlandish and German paintings', 'titles': [u'Early Netherlandish and German paintings', u'early netherlandish and german paintings'], 'publish_date': '1985', 'authors': [{'db_name': u'National Gallery (Great Britain)', 'name': u'National Gallery (Great Britain)', 'entity_type': 'org'}], 'number_of_pages': 116, 'by_statement': 'Alistair Smith.', 'source_record_loc': 'marc_records_scriblio_net/part17.dat:170029527:1210'}
    threshold = 735
    assert attempt_merge(amazon, marc, threshold)

def test_compare_authors():
    amazon = {'authors': [(u'Alistair Smith', u'Author')]}
    marc = {'authors': [{'db_name': u'National Gallery (Great Britain)', 'name': u'National Gallery (Great Britain)', 'entity_type': 'org'}], 'by_statement': 'Alistair Smith.'}
    assert compare_authors(amazon, marc) == ('authors', 'exact match', 125)

def test_merge6():
    amazon = {'publishers': [u'Fount'], 'isbn_10': ['0002176157'], 'number_of_pages': 224, 'short_title': u'basil hume', 'normalized_title': u'basil hume', 'full_title': u'Basil Hume', 'titles': [u'Basil Hume', u'basil hume'], 'publish_date': u'1986', 'authors': [(u'Tony Castle', u'Editor')]}
    marc = {'publisher': [u'Collins'], 'isbn_10': [u'0002176157'], 'short_title': u'basil hume  a portrait', 'normalized_title': u'basil hume  a portrait', 'full_title': u'Basil Hume : a portrait', 'titles': [u'Basil Hume : a portrait', u'basil hume  a portrait'], 'number_of_pages': 158, 'publish_date': '1986', 'by_statement': 'edited by Tony Castle.', 'source_record_loc': 'marc_records_scriblio_net/part19.dat:39883132:951'}
    threshold = 735
    assert attempt_merge(amazon, marc, threshold)

def test_merge7():
    amazon = {'publishers': [u'HarperCollins Publishers Ltd'], 'isbn_10': ['0002176319'], 'number_of_pages': 256, 'short_title': u'pucklers progress', 'normalized_title': u'pucklers progress', 'full_title': u"Puckler's Progress", 'titles': [u"Puckler's Progress", u'pucklers progress'], 'publish_date': u'1987', 'authors': [(u'Flora Brennan', u'Editor')]}
    marc = {'publisher': [u'Collins'], 'isbn_10': [u'0002176319'], 'short_title': u'pucklers progress  the ad', 'normalized_title': u'pucklers progress  the adventures of prince puckler muskau in england wales and ireland as told in letters to his former wife 1826 9', 'full_title': u"Puckler's progress : the adventures of Prince Pu\u0308ckler-Muskau in England, Wales, and Ireland as told in letters to his former wife, 1826-9", 'titles': [u"Puckler's progress : the adventures of Prince Pu\u0308ckler-Muskau in England, Wales, and Ireland as told in letters to his former wife, 1826-9", u'pucklers progress  the adventures of prince puckler muskau in england wales and ireland as told in letters to his former wife 1826 9'], 'publish_date': '1987', 'authors': [{'name': u'Pu\u0308ckler-Muskau, Hermann Furst von', 'title': u'Furst von', 'death_date': u'1871.', 'db_name': u'Pu\u0308ckler-Muskau, Hermann Furst von 1785-1871.', 'birth_date': u'1785', 'personal_name': u'Pu\u0308ckler-Muskau, Hermann', 'entity_type': 'person'}], 'number_of_pages': 254, 'by_statement': 'translated by Flora Brennan.', 'source_record_loc': 'marc_records_scriblio_net/part19.dat:148554594:1050'}
    threshold = 735
    assert attempt_merge(amazon, marc, threshold)

def test_compare_publisher():
    amazon = { 'publishers': ['foo'] }
    amazon2 = { 'publishers': ['bar'] }
    marc = { 'publishers': ['foo'] }
    marc2 = { 'publishers': ['foo', 'bar'] }
    assert compare_publisher({}, {}) == ('publisher', 'either missing', 0)
    assert compare_publisher(amazon, {}) == ('publisher', 'either missing', 0)
    assert compare_publisher({}, marc) == ('publisher', 'either missing', 0)
    assert compare_publisher(amazon, marc) == ('publisher', 'match', 100)
    assert compare_publisher(amazon2, marc) == ('publisher', 'mismatch', -25)
    assert compare_publisher(amazon2, marc2) == ('publisher', 'match', 100)

def test_merge8():
    amazon = {'publishers': [u'Shambhala'], 'isbn': [u'1590301390'], 'number_of_pages': 144, 'short_title': u'the spiritual teaching of', 'normalized_title': u'the spiritual teaching of ramana maharshi', 'full_title': u'The Spiritual Teaching of Ramana Maharshi', 'titles': [u'The Spiritual Teaching of Ramana Maharshi', u'the spiritualteaching of ramana maharshi', u'Spiritual Teaching of Ramana Maharshi', u'spiritual teaching of ramana maharshi'], 'publish_date': u'2004', 'authors': [u'Ramana Maharshi.']}
    marc = {'isbn': [], 'number_of_pages': 180, 'short_title': 'the spiritual teaching of', 'normalized_title': 'the spiritual teaching of mary of the incarnation', 'full_title': 'The spiritual teaching of Mary of the Incarnation', 'titles': ['The spiritual teaching of Mary of the Incarnation', 'the spiritual teaching of mary of the incarnation', 'spiritual teaching of Mary of the Incarnation', 'spiritual teaching of mary of the incarnation'], 'publish_date': '1963', 'publish_country': 'nyu', 'authors': [{'db_name': 'Jett\xc3\xa9, Fernand.', 'name': 'Jett\xc3\xa9, Fernand.'}]}
    threshold = 735
    assert attempt_merge(amazon, marc, threshold)

#test_merge8()
