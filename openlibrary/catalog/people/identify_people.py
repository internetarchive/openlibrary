from openlibrary.catalog.marc.cmdline import fmt_subfields
from openlibrary.catalog.marc.fast_parse import get_subfields, get_all_subfields
from openlibrary.catalog.utils import remove_trailing_dot, remove_trailing_number_dot, match_with_bad_chars, pick_first_date
import openlibrary.catalog.utils.authority as authority
from openlibrary.catalog.merge.normalize import normalize
from collections import defaultdict
from pprint import pprint
import re

def strip_death(date):
    return date[:date.rfind('-')+1]

def test_strip_death():
    assert strip_death("1850-1910") == "1850-"

re_dates = re.compile(' (\d{2,4}-(?:\d{2,4})?)$')
re_dates_in_field = re.compile('^(\d{2,4})-((?:\d{2,4})?)$')
re_dates_in_field_bc = re.compile('^(\d{2,4}) B\.C\.-((?:\d{2,4}) B\.C\.?)$')

def test_transpose_date():
    assert transpose_date(u'1452') == u'1425'

def transpose_date(date):
    return date[:-2] + date[-1] + date[-2]

def is_date_transposed(d1, d2):
    m1 = re_dates_in_field.match(d1)
    m2 = re_dates_in_field.match(d2)
    if not m1 and not m2:
        m1 = re_dates_in_field_bc.match(d1)
        m2 = re_dates_in_field_bc.match(d2)
    if not m1 or not m2:
        return False

    if m1.group(1) == m2.group(1):
        death1 = m1.group(2)
        death2 = m2.group(2)
        if not death1 or not death2:
            return False
        return transpose_date(death1) == death2
    if m1.group(2) == m2.group(2):
        birth1 = m1.group(1)
        birth2 = m2.group(1)
        return transpose_date(birth1) == birth2
    return False

def test_is_date_transposed():
    assert is_date_transposed(u'1452-1485', u'1425-1485')

def dates_not_close(d1, d2):
    m1 = re_dates_in_field.match(d1)
    if not m1:
        return False
    m2 = re_dates_in_field.match(d2)
    if not m2:
        return False

    birth1 = int(m1.group(1))
    birth2 = int(m2.group(1))
    if abs(birth1 - birth2) >= 10:
        return True

    if not m1.group(2) or not m2.group(2):
        return False

    death1 = int(m1.group(2))
    death2 = int(m2.group(2))
    return abs(death1 - death2) >= 10

def test_dates_not_close():
    assert dates_not_close('1825-1899', '1804-1849') 
    assert not dates_not_close(u'1907-2003', u'1909-')
    assert not dates_not_close('1825-1899', '1826-1898') 

def combinations(iterable, r):
    # combinations('ABCD', 2) --> AB AC AD BC BD CD
    # combinations(range(4), 3) --> 012 013 023 123
    pool = tuple(iterable)
    n = len(pool)
    if r > n:
        return
    indices = range(r)
    yield tuple(pool[i] for i in indices)
    while True:
        for i in reversed(range(r)):
            if indices[i] != i + n - r:
                break
        else:
            return
        indices[i] += 1
        for j in range(i+1, r):
            indices[j] = indices[j-1] + 1
        yield tuple(pool[i] for i in indices)

def tidy_subfield(v):
    return remove_trailing_dot(v.strip(' /,;:'))

re_bc_date = re.compile('(\d+)B\.C\.')

def clean_subfield(k, v):
    if k in 'abc':
        v = tidy_subfield(v)
    elif k == 'd':
        v = remove_trailing_number_dot(v.strip(' ,'))
        v = re_bc_date.sub(lambda m: m.group(1) + " B.C.", v)
    return (k, v)

def has_subtag(a, subfields):
    return any(k==a for k, v in subfields)

def question_date(p1, p2):
    marc_date1 = tuple(v for k, v in p1 if k =='d')
    if not marc_date1:
        return
    marc_date2 = tuple(v for k, v in p2 if k =='d')
    if not marc_date1 or not marc_date2 or marc_date1 == marc_date2:
        return

    assert len(marc_date1) == 1 and len(marc_date2) == 1

    name1 = tuple((k, v) for k, v in p1 if k !='d')
    name2 = tuple((k, v) for k, v in p2 if k !='d')
    if name1 != name2:
        return

    marc_date1 = marc_date1[0]
    question1 = '?' in marc_date1

    marc_date2 = marc_date2[0]
    question2 = '?' in marc_date2

    if (not question1 and not question2) or (question1 and question2):
        return # xor

    if marc_date1.replace('?', '') != marc_date2.replace('?', ''):
        return
    return 1 if question1 else 2

def get_marc_date(p):
    marc_date = tuple(v for k, v in p if k =='d')
    if not marc_date:
        return
    assert len(marc_date) == 1
    return marc_date[0].strip()

def build_by_name(found):
    by_name = defaultdict(set)
    for p in found:
        if has_subtag('d', p):
            without_date = tuple(i for i in p if i[0] != 'd')
            by_name[without_date].add(p)

    return by_name

def build_name_and_birth(found):
    # one author missing death date
    name_and_birth = defaultdict(set)
    for p in found:
        d = get_marc_date(p)
        if not d or d[-1] == '-' or '-' not in d:
            continue
        without_death = tuple((k, (v if k!='d' else strip_death(v))) for k, v in p)
#        assert without_death not in name_and_birth
        name_and_birth[without_death].add(p)
    return name_and_birth

def authority_lookup(to_check, found, marc_alt):
    found_matches = False
    for person_key, match in to_check.items():
        if len(match) == 1:
            continue
        if len(match) == 2:
            d1, d2 = [get_marc_date(p) for p in match]
            if dates_not_close(d1, d2) and not is_date_transposed(d1, d2):
                continue

        name = ' '.join(v.strip() for k, v in person_key if k != 'd')
        search_results = authority.search(name)
        match_dates = dict((get_marc_date(p), p) for p in match)
        norm_name = normalize(name)
        authority_match = None
        for i in search_results:
            if i['type'] != 'personal name' or i['a'] == 'reference':
                continue
            if norm_name not in normalize(i['heading']):
                continue
            for d, p in match_dates.items():
                if i['heading'].endswith(d):
                    if authority_match: # more than one match
                        print 'dups:', match_dates.items()
                        authority_match = None
                        break
                    authority_match = p
        if authority_match:
            for p in match:
                if p == authority_match:
                    continue
                found[authority_match] += found.pop(p)
                marc_alt[p] = authority_match
                found_matches = True
    return found_matches

def subtag_should_be_c(found, marc_alt):
    merge = []
    for p1, p2 in combinations(found, 2):
        if len(p1) != len(p2):
            continue

        subtag1 = [k for k, v in p1 if k in 'abcdq']
        subtag2 = [k for k, v in p2 if k in 'abcdq']

        if subtag1 == subtag2:
            continue

        def no_question_if_d(p):
            return [v.replace('?', '') if k == 'd' else tidy_subfield(v) for k, v in p]
        if no_question_if_d(p1) != no_question_if_d(p2):
            continue

        for i in range(len(subtag1)):
            if subtag1[i] == subtag2[i]:
                continue
            assert len(p1[i][1]) >= 5

            if subtag1[i] == 'c':
                assert subtag2[i] in 'bq'
                merge.append((p1, p2))
            else:
                assert subtag1[i] in 'bq' and subtag2[i] == 'c'
                merge.append((p2, p1))
            break

    for a, b in merge:
        if b not in found:
            continue
        found[a] += found.pop(b)
        marc_alt[b] = a

def merge_question_date(found, marc_alt):
    merge = []
    for p1, p2 in combinations(found, 2):
        primary = question_date(p1, p2)
        if primary is None:
            continue
        if primary == 1:
            merge.append((p1, p2))
        else:
            assert primary == 2
            merge.append((p2, p1))

    for a, b in merge:
        found[a] += found.pop(b)
        marc_alt[b] = a

re_bad_marc = re.compile(' ?\$ ?[a-z] ')
def remove_bad_marc_subtag(s):
    s = re_bad_marc.sub(' ', s)
    return s

def test_remove_bad_marc_subtag():
    assert remove_bad_marc_subtag('John, $ c King of England') == 'John, King of England'


def just_abcdq(p):
    return tuple((k, v) for k, v in p if k in 'abcdq')

def similar_dates(found, marc_alt):
    # 1516 == d. 1516
    merge = []
    for p1, p2 in combinations(found, 2):
        subtag1 = [k for k, v in p1]
        subtag2 = [k for k, v in p2]
        if subtag1 != subtag2:
            continue
        if [(k, v) for k, v in p1 if k != 'd'] != [(k, v) for k, v in p2 if k != 'd']:
            continue
        d1 = [v for k, v in p1 if k == 'd']
        d2 = [v for k, v in p2 if k == 'd']
        if d1 == d2:
            continue
        assert len(d1) == 1 and len(d2) == 1
        d1, d2 = d1[0], d2[0]
        if d1 == 'd. ' + d2:
            merge.append((p1, p2))
            continue
        if d2 == 'd. ' + d1:
            merge.append((p2, p1))
            continue

    for a, b in merge:
        if b not in found:
            continue
        found[a] += found.pop(b)
        marc_alt[b] = a

re_simple_date = re.compile('^(\d+)-(\d+)?\.?$')

def fix_bad_subtags(found, marc_alt):
    just_values = defaultdict(lambda:defaultdict(int))
    for p, num in found.items():
        just_values[tuple(v.strip(',') for k, v in p)][p] += num

    for a, b in just_values.items():
        if len(b) == 1:
            continue
        b = sorted(b.items(), key=lambda i:i[1])
        if b[-1][1] == b[-2][1]:
            continue
        new = b.pop()[0]
        for i, j in b:
            found[new] += found.pop(i)
            marc_alt[i] = new

def wrong_subtag_on_date(found, marc_alt):
    for p in found.keys():
        found_simple_date = False
        for k, v in p:
            if k != 'd' and re_simple_date.match(v):
                found_simple_date = True
                break
        if not found_simple_date:
            continue
        new = tuple((('d' if k !='d' and re_simple_date.match(v) else k), v) for k, v in p)
        if new in found:
            found[new] += found.pop(p)
            marc_alt[p] = new

def missing_subtag(found, marc_alt):
    merge = defaultdict(set)
    for p1, p2 in combinations(found, 2):
        subtag1 = [k for k, v in p1 if k in 'abcdq']
        subtag2 = [k for k, v in p2 if k in 'abcdq']

        if subtag1 == subtag2:
            continue

        name1 = ' '.join(v.strip() for k, v in p1)
        name2 = ' '.join(v.strip() for k, v in p2)

        if not match_with_bad_chars(name1, name2) \
                and normalize(name1) != normalize(name2) \
                and normalize(remove_bad_marc_subtag(name1)) != normalize(remove_bad_marc_subtag(name2)) \
                and normalize(name1.lower().replace(' the', '')) != normalize(name2.lower().replace(' the', '')):
            continue

        if len(subtag1) > len(subtag2):
            merge[p2].add(just_abcdq(p1))
        else:
            merge[p1].add(just_abcdq(p2))

    def flat_len(p):
        return len(' '.join(v for k, v in p))

    for old, new in merge.items():
        by_size = sorted((flat_len(p), p) for p in new)
        if len(by_size) > 1:
            assert by_size[-1][0] > by_size[-2][0]
        new_marc = by_size[-1][1]

        found[new_marc] += found.pop(old)
        marc_alt[old] = new_marc

def date_field_missing(p):
    if has_subtag('d', p):
        return p
    assert has_subtag('a', p)
    for k, v in p:
        if k == 'a':
            a = v
            break
    m = re_dates.search(a)
    if not m:
        return p
    d = m.group(1)
    a = tidy_subfield(a[:m.start()])
    new = []
    for k, v in p:
        if k == 'a' and a:
            new.append(('a', a))
            a = None
            continue
        if k not in ('b', 'c') and d:
            new.append(('d', d))
            d = None
        new.append((k, v))
    if d:
        new.append(('d', d))
    return tuple(new)

def bad_char_name_match(found, marc_alt):
    merge = []
    for p1, p2 in combinations(found, 2):
        if p1 == p2:
            continue
        if get_marc_date(p1) != get_marc_date(p2):
            continue
        p1, p2 = sorted([p1, p2], key=lambda i:found[i])
        if found[p1] != found[p2]:
            name1 = ' '.join(v for k, v in p1 if k in 'abc')
            name2 = ' '.join(v for k, v in p2 if k in 'abc')
            if match_with_bad_chars(name1, name2):
                found[p2] += found.pop(p1)
                marc_alt[p1] = p2

    for a, b in merge:
        if b not in found:
            continue
        found[a] += found.pop(b)
        marc_alt[b] = a

def check_for_dup_a(p):
    for a1, a2 in combinations((v for k, v in p if k == 'a'), 2):
        assert a1 != a2

def read_people(people):
    found = defaultdict(int)
    marc_alt = {}
    people = list(people)

    for lines in people:
        for line in lines:
            p = tuple(clean_subfield(k, v) for k, v in get_all_subfields(line))
            #check_for_dup_a(p)
            found[date_field_missing(p)]+=1

    for p in found.keys():
        c = None
        for k, v in p:
            if k == 'c':
                c = v
                break
        if not c or c.lower() != 'family':
            continue
        new = tuple((k, v + ' family' if k == 'a' else v) for k, v in p if k != 'c') 
        if new in found:
            found[new] += found.pop(p)
            marc_alt[p] = new

    fix_bad_subtags(found, marc_alt)

    wrong_subtag_on_date(found, marc_alt)

    try:
        missing_subtag(found, marc_alt)
    except AssertionError:
        print people
        raise

    found_name = defaultdict(int)
    for p, num in found.items():
        found_name[just_abcdq(p)] += num
    found = found_name

    assert found

    if len(found) == 1:
        return dict(found), marc_alt

    #for func in subtag_should_be_c, merge_question_date:
    #for func in subtag_should_be_c, merge_question_date, missing_subtag, bad_char_name_match:
    for func in subtag_should_be_c, merge_question_date, bad_char_name_match, similar_dates:
        func(found, marc_alt)

        if len(found) == 1:
            return dict(found), marc_alt

    assert found

    # one author missing death date
    name_and_birth = build_name_and_birth(found)

    assert found

    try:
        if authority_lookup(name_and_birth, found, marc_alt):
            if len(found) == 1:
                return dict(found), marc_alt

            name_and_birth = build_name_and_birth(found)
    except AssertionError:
        print people
        raise

    assert found

    for p, num in found.items():
        if p not in name_and_birth:
            continue
        assert len(name_and_birth[p]) == 1
        new_name = list(name_and_birth[p])[0]
        found[new_name] += found.pop(p)
        marc_alt[p] = new_name

    assert found

    if len(found) == 1:
        return dict(found), marc_alt

    # match up authors with the same name
    # where one has dates and the other doesn't
    by_name = build_by_name(found)

    try:
        if authority_lookup(by_name, found, marc_alt):
            if len(found) == 1:
                return dict(found), marc_alt
            by_name = build_by_name(found) # rebuild
    except AssertionError:
        print people
        raise

    for p, num in found.items():
        if p not in by_name:
            continue
        if len(by_name[p]) != 1:
            for i in by_name[p]:
                print i
            print people
        assert len(by_name[p]) == 1
        new_name = list(by_name[p])[0]
        found[new_name] += found.pop(p)
        marc_alt[p] = new_name
    assert found

    if len(found) == 1:
        return dict(found), marc_alt

    by_date = defaultdict(set)
    for p in found:
        if not has_subtag('d', p):
            continue
        d = tuple(v for k, v in p if k=='d')
        by_date[d].add(p)
#    for k, v in by_date.iteritems():
#        print len(v), k, v

    return dict(found), marc_alt

def read_files():
    read_file('work_and_marc2')
    read_file('work_and_marc3')

def read_file(filename):
    for file_line in open(filename):
        w = eval(file_line)
        if len(w['lines']) == 1:
            continue
        lines = [i[1] for i in w['lines']]
        print w['key'], w['title']
        print lines
        people, marc_alt = read_people(lines)
#        for p, num in people.iteritems():
#            if any(k=='d' for k, v in people):
#                continue
        for p, num in people.iteritems():
            print '  %2d %s' % (num, ' '.join("%s: %s" % (k, v) for k, v in p))
            print '     ', p
        print
#read_file()

def test_accents():
    lines = [
        ['00\x1faB\xe5adar\xe5aya\xf2na.\x1ftBrahmas\xe5utra.\x1e'], 
        ['00\x1faB\xe5adar\xe5aya\xf2na.\x1ftBrahmas\xe5utra.\x1e'], 
        ['00\x1faB\xe5adar\xe5aya\xf2na.\x1ftBrahmas\xe5utra.\x1e'], 
        ['00\x1faB\xe5adar\xe5aya\xf2na.\x1ftBrahmas\xe5utra.\x1e'], 
        ['00\x1faB\xe5adar\xe5aya\xf2na.\x1ftBrahmas\xe5utra.\x1e'], 
        ['00\x1faB\xe5adar\xe5ayana.\x1ftBrahmas\xe5utra.\x1e']
    ]
    a, b = read_people(lines)
    assert a == {(('a', u'B\u0101dar\u0101ya\u1e47a'),): 6}
    assert b == { (('a', u'B\u0101dar\u0101yana'),): (('a', u'B\u0101dar\u0101ya\u1e47a'),)}

def test_same_name_one_date_missing():
    lines = [
        ['10\x1faAbedin, Zainul\x1fxCriticism and interpretation.\x1e'], 
        ['10\x1faAbedin, Zainul,\x1fd1914-1976\x1fxCriticism and interpretation.\x1e'],

        ['10\x1faAbedin, Zainul\x1fxCriticism and interpretation.\x1e'], 
        ['10\x1faAbedin, Zainul,\x1fd1914-1976\x1fxCriticism and interpretation.\x1e']
    ]
    a, b = read_people(lines)

    assert a == {(('a', u'Abedin, Zainul'), ('d', u'1914-1976')): 4}
    assert b == {(('a', u'Abedin, Zainul'),): (('a', u'Abedin, Zainul'), ('d', u'1914-1976'))}

def test_matching_name_missing_death():
    lines = [
        ['10\x1faFrisch, Max,\x1fd1911-1991\x1e'],
        ['10\x1faFrisch, Max,\x1fd1911-\x1e'],
        ['10\x1faFrisch, Max,\x1fd1911-\x1e']
    ]
    a, b = read_people(lines)
    assert a == {(('a', u'Frisch, Max'), ('d', u'1911-1991')): 3}
    assert b == {(('a', u'Frisch, Max'), ('d', u'1911-')): (('a', u'Frisch, Max'), ('d', u'1911-1991'))}

def test_matching_dates():
    lines = [
        ['00\x1faMichelangelo Buonarroti,\x1fd1475-1564.\x1e'],
        ['00\x1faMichelangelo Buonarroti,\x1fd1475-1564.\x1e'],
        ['16\x1faBuonarroti, Michel Angelo,\x1fd1475-1564.\x1e']
    ]
    a, b = read_people(lines)

def test_harold_osman_kelly():
    lines = [
        ['10\x1faKelly, Harold Osman,\x1fd1884-1955.\x1e'],
        ['10\x1faKelly, Harold Osman,\x1fd1884-1956.\x1e']
    ]
    a, b = read_people(lines)
    assert a == {(('a', u'Kelly, Harold Osman'), ('d', u'1884-1955')): 2}
    assert b == {(('a', u'Kelly, Harold Osman'), ('d', u'1884-1956')): (('a', u'Kelly, Harold Osman'), ('d', u'1884-1955'))}

def test_question_date():
    lines = [
        ['10\x1faBurke, Edmund,\x1fd1729?-1797.\x1ftReflections on the revolution in France.\x1e', '10\x1faCalonne,\x1fcM. de\x1fq(Charles Alexandre de),\x1fd1734-1802.\x1e'],
        ['10\x1faBurke, Edmund,\x1fd1729-1797.\x1ftReflections on the Revolution in France.\x1e']
    ]
    a, b = read_people(lines)
    assert a == {
        (('a', u'Burke, Edmund'), ('d', u'1729?-1797')): 2,
        (('a', u'Calonne'), ('c', u'M. de'), ('q', u'(Charles Alexandre de),'), ('d', u'1734-1802')): 1
    }

    assert b == {
        (('a', u'Burke, Edmund'), ('d', u'1729-1797')): (('a', u'Burke, Edmund'), ('d', u'1729?-1797'))
    }


def test_pope_sixtus():
    lines = [
        ['00\x1faSixtus\x1fbV,\x1fcPope,\x1fd1521-1590.\x1e'], 
        ['04\x1faSixtus\x1fbV,\x1fcPope.\x1e'],
        ['00\x1faSixtus\x1fbV,\x1fcPope,\x1fd1520-1590.\x1e']
    ]
    a, b = read_people(lines)
    assert a == {
        ((u'a', u'Sixtus'), (u'b', u'V'), (u'c', u'Pope'), (u'd', u'1520-1590')): 3
    }

    assert b == {
        (('a', u'Sixtus'), ('b', u'V'), ('c', u'Pope')): (('a', u'Sixtus'), ('b', u'V'), ('c', u'Pope'), ('d', u'1520-1590')),
        (('a', u'Sixtus'), ('b', u'V'), ('c', u'Pope'), ('d', u'1521-1590')): (('a', u'Sixtus'), ('b', u'V'), ('c', u'Pope'), ('d', u'1520-1590'))
    }

def test_william_the_conqueror():
    lines = [
        ['00\x1faWilliam\x1fbI,\x1fcKing of England,\x1fd1027 or 8-1087.\x1e'], ['04\x1faWilliam\x1fbI,\x1fcKing of England,\x1fd1027?-1087.\x1e'],
        ['00\x1faWilliam\x1fbI,\x1fcKing of England,\x1fd1027 or 8-1087.\x1e'], ['00\x1faWilliam\x1fbI,\x1fcKing of England,\x1fd1027 or 8-1087\x1e'],
        ['00\x1faWilliam\x1fbI,\x1fcKing of England,\x1fd1027 or 8-1087.\x1e'], ['00\x1faWilliam\x1fbI,\x1fcKing of England,\x1fd1027 or 8-1087.\x1e']
    ]
    a, b = read_people(lines)

    assert a == {(('a', u'William'), ('b', u'I'), ('c', u'King of England'), ('d', u'1027 or 8-1087')): 6}
    assert b == {(('a', u'William'), ('b', u'I'), ('c', u'King of England'), ('d', u'1027?-1087')): (('a', u'William'), ('b', u'I'), ('c', u'King of England'), ('d', u'1027 or 8-1087'))}

def test_missing_d():
    lines = [
        [' 0\x1faDickens, Charles, 1812-1870\x1fxManuscripts\x1fxFacsimiles.\x1e'],
        ['10\x1faDickens, Charles,\x1fd1812-1870\x1fxManuscripts\x1fxFacsimiles.\x1e']
    ]
    a, b = read_people(lines)
    assert a == {(('a', u'Dickens, Charles'), ('d', u'1812-1870')): 2}
    #assert b == {(('a', u'Dickens, Charles, 1812-1870'),): (('a', u'Dickens, Charles'), ('d', u'1812-1870'))}
    assert b == {}

def test_missing_c():
    return # skip for now
    lines = [
        ['00\x1faMuhammad Quli Qutb Shah,\x1fcSultan of Golkunda,\x1fd1565-1612.\x1e'],
        ['00\x1faMuhammad Quli Qutb Shah,\x1fcSultan of Golkunda,\x1fd1565-1612.\x1e'],
        ['10\x1faMuhammad Quli Qutb Shah, Sultan of Golconda,\x1fd1565-1612\x1e']
    ]
    a, b = read_people(lines)
    assert a == {(('a', u'Muhammad Quli Qutb Shah'), ('c', u'Sultan of Golkunda'), ('d', u'1565-1612')): 3}

def test_same_len_subtag():
    lines = [
        ['00\x1faJohn,\x1fcKing of England,\x1fd1167-1216\x1e', '10\x1faShakespeare, William,\x1fd1564-1616\x1fxStage history\x1e'],
        ['00\x1faJohn,\x1fcKing of England,\x1fd1167-1216\x1fxDrama.\x1e', '10\x1faShakespeare, William,\x1fd1564-1616\x1fxStage history.\x1e'],
        ['00\x1faJohn\x1fbKing of England,\x1fd1167-1216\x1fxDrama.\x1e', '10\x1faShakespeare, William,\x1fd1564-1616\x1fxStage history.\x1e']
    ]
    a, b = read_people(lines)
    assert a == {
        (('a', u'John'), ('c', u'King of England'), ('d', u'1167-1216')): 3,
        (('a', u'Shakespeare, William'), ('d', u'1564-1616')): 3
    }

def test_king_john():
    lines = [
        ['00\x1faJohn,\x1fcKing of England,\x1fd1167-1216\x1fxDrama.\x1e'],
        ['00\x1faJohn,\x1fcKing of England,\x1fd1167-1216\x1fxDrama\x1e', '10\x1faKean, Charles John,\x1fd1811?-1868\x1e'],
        ['00\x1faJohn,\x1fcKing of England,\x1fd1167-1216\x1fxDrama\x1e'],
        ['00\x1faJohn\x1fbKing of England,\x1fd1167-1216\x1fxDrama.\x1e'],
        ['00\x1faJohn,\x1fcKing of England,\x1fd1167?-1216\x1fxDrama.\x1e'],
        ['00\x1faJohn\x1fbKing of England,\x1fd1167-1216\x1fxDrama.\x1e'],
        ['00\x1faJohn\x1fbKing of England,\x1fd1167-1216\x1fxDrama.\x1e'],
        ['00\x1faJohn,\x1fcKing of England,\x1fd1167-1216\x1fvDrama.\x1e'],
        ['00\x1faJohn\x1fbKing of England,\x1fd1167-1216\x1fvDrama.\x1e'],
        ['00\x1faJohn,\x1fcKing of England,\x1fd1167?-1216\x1fxDrama.\x1e'],
        ['00\x1faJohn,\x1fcKing of England,\x1fd1167?-1216\x1fxDrama.\x1e'],
        ['00\x1faJohn,\x1fcKing of England,\x1fd1167?-1216\x1fxDrama.\x1e'],
        ['00\x1faJohn,\x1fcKing of England,\x1fd1167-1216\x1fvDrama\x1e'],
        ['00\x1faJohn,\x1fcKing of England,\x1fd1167-1216\x1fvDrama.\x1e'],
        ['00\x1faJohn,\x1fcKing of England,\x1fd1167?-1216\x1fxDrama.\x1e'],
        ['00\x1faJohn,\x1fcKing of England,\x1fd1167-1216\x1fxDrama.\x1e'],
        ['00\x1faJohn,\x1fcKing of England,\x1fd1167-1216\x1fxDrama.\x1e'],
        ['00\x1faJohn,\x1fcKing of England,\x1fd1167-1216\x1fvDrama.\x1e'],
        ['00\x1faJohn,\x1fcKing of England,\x1fd1167-1216\x1fxDrama.\x1e'],
        ['00\x1faJohn\x1fbKing of England,\x1fd1167-1216\x1fxDrama.\x1e'],
        ['00\x1faJohn,\x1fcKing of England,\x1fd1167?-1216\x1fvDrama.\x1e', '00\x1faHenry\x1fbVIII,\x1fcKing of England,\x1fd1491-1547\x1fvDrama.\x1e'],
        ['00\x1faJohn,\x1fcKing of England,\x1fd1167-1216\x1fvDrama.\x1e'],
        ['00\x1faJohn,\x1fcKing of England,\x1fd1167-1216\x1fvDrama.\x1e'],
        ['00\x1faJohn\x1fbKing of England,\x1fd1167-1216\x1fxDrama.\x1e'],
        ['14\x1faShakespeare, William,\x1fd1564-1616.\x1ftKing John.\x1e'],
        ['00\x1faJohn,\x1fcKing of England,\x1fd1167-1216\x1fvDrama.\x1e', '10\x1faShakespeare, William,\x1fd1564-1616.\x1ftKing John.\x1e'],
        ['00\x1faJohn,\x1fcKing of England,\x1fd1167-1216\x1fxDrama\x1e'],
        ['00\x1faJohn,\x1fcKing of England,\x1fd1167-1216\x1fvDrama.\x1e'],
        ['00\x1faJohn,\x1fcKing of England,\x1fd1167-1216\x1fxDrama\x1e', '00\x1faHenry\x1fbVIII,\x1fcKing of England,\x1fd1491-1547\x1fxDrama\x1e'],
        ['00\x1faJohn,\x1fcKing of England,\x1fd1167-1216\x1fxDrama.\x1e'],
        ['00\x1faJohn,\x1fcKing of England,\x1fd1167?-1216\x1fxDrama.\x1e'],
        ['00\x1faJohn,\x1fcKing of England,\x1fd1167-1216\x1fxDrama.\x1e', '10\x1faShakespeare, William,\x1fd1564-1616.\x1fxKing John\x1fxProblems, exercises, etc.\x1e', '01\x1faJohn,\x1fcKing of England,\x1fd1167-1216\x1fxDrama.\x1e'],
        ['00\x1faJohn, $ c King of England,\x1fd1167-1216\x1fxDrama\x1e'],
        ['00\x1faJohn, $ c King of England,\x1fd1167-1216\x1fxDrama\x1e'],
        ['00\x1faJohn\x1fbKing of England,\x1fd1167-1216\x1fxDrama.\x1e']
    ]
    a, b = read_people(lines)
    assert a == {
        (('a', u'Shakespeare, William'), ('d', u'1564-1616')): 3,
        (('a', u'Kean, Charles John'), ('d', u'1811?-1868')): 1,
        (('a', u'John'), ('c', u'King of England'), ('d', u'1167?-1216')): 35,
        (('a', u'Henry'), ('b', u'VIII'),('c', u'King of England'), ('d', u'1491-1547')): 2
    }

def test_non_ascii():
    lines = [
        ['00\x1faA\xe2soka,\x1fcKing of Magadha,\x1fdfl. 259 B.C.\x1e'],
        ['00\x1faA{acute}soka,\x1fcKing of Magadha\x1fdfl. 259 B.C.\x1e'],
        ['00\x1faAsoka,\x1fcKing of Magadha,\x1fdfl. 259 B.C..\x1e', '30\x1faMaurya family.\x1e'],
        ['04\x1faAs\xcc\x81oka,\x1fcKing of Magadha,\x1fdca. 274-232 B.C.\x1e'],
        ['00\x1faA\xe2soka,\x1fcKing of Magadha,\x1fdfl. 259 B.C.\x1e', '30\x1faMaurya dynasty.\x1e'],
        ['04\x1faAsoka,\x1fcKing of Magadha,\x1fdca. 274-232 B.C.\x1e'],
        ['00\x1faA\xe2soka,\x1fcKing of Magadha,\x1fdfl. 259 B.C\x1e', '30\x1faMaurya dynasty\x1e'],
        ['00\x1faAs\xcc\x81oka,\x1fcKing of Magadha,\x1fdfl. 259 B.C.\x1e', '30\x1faMaurya family.\x1e']
    ]
    a, b = read_people(lines)
    print a

def test_q_should_be_c():
    lines = [
        ['10\x1faLafayette, Marie Joseph Paul Yves Roch Gilbert Du Motier,\x1fcmarquis de,\x1fd1757-1834\x1fxTravel\x1fzNew York (State)\x1fzNew York.\x1e'],
        ['10\x1faLafayette, Marie Joseph Paul Yves Roch Gilbert Du Motier,\x1fcmarquis de,\x1fd1757-1834\x1fxTravel\x1fzNew York (State)\x1fzNew York.\x1e'],
        ['10\x1faLafayette, Marie Joseph Paul Yves Roch Gilbert Du Motier,\x1fqmarquis de,\x1fd1757-1834.\x1e']
    ]
    a, b = read_people(lines)

def test_date_in_a():
    lines = [
        ['10\x1faMachiavelli, Niccol\xe1o,\x1fd1469-1527\x1fxFiction.\x1e', '10\x1faBorgia, Cesare,\x1fd1476?-1507\x1fxFiction.\x1e'],
        [' 0\x1faBorgia, Cesare, 1476?-1507\x1fxFiction.\x1e', ' 0\x1faMachiavelli, Niccolo, 1469-1527\x1fxFiction.\x1e'],
        ['10\x1faMachiavelli, Niccol\xe1o,\x1fd1469-1527\x1fxFiction.\x1e', '10\x1faBorgia, Cesare,\x1fd1476?-1507\x1fxFiction.\x1e'],
        ['10\x1faMachiavelli, Niccol\xe1o,\x1fd1469-1527\x1fxFiction.\x1e', '10\x1faBorgia, Cesare,\x1fd1476?-1507\x1fxFiction.\x1e'], ['10\x1faMachiavelli, Niccol\xe1o,\x1fd1469-1527\x1fxFiction.\x1e', '10\x1faBorgia, Cesare,\x1fd1476?-1507\x1fxFiction.\x1e'], ['10\x1faMachiavelli, Niccol\xe1o,\x1fd1469-1527\x1fxFiction\x1e', '10\x1faBorgia, Cesare,\x1fd1476?-1507\x1fxFiction\x1e'],
        ['10\x1faMachiavelli, Niccol\xe1o,\x1fd1469-1527\x1fxFiction.\x1e', '10\x1faBorgia, Cesare,\x1fd1476?-1507\x1fxFiction.\x1e']
    ]
    a, b = read_people(lines)
    print a
    assert a == {(('a', u'Borgia, Cesare'), ('d', u'1476?-1507')): 7, (('a', u'Machiavelli, Niccol\xf2'), ('d', u'1469-1527')): 7}

def test_king_asoka():
    return
    lines = [
        ['00\x1faA\xe2soka,\x1fcKing of Magadha,\x1fdfl. 259 B.C.\x1e'],
        ['00\x1faA{acute}soka,\x1fcKing of Magadha\x1fdfl. 259 B.C.\x1e'],
        ['00\x1faAsoka,\x1fcKing of Magadha,\x1fdfl. 259 B.C..\x1e', '30\x1faMaurya family.\x1e'],
        ['04\x1faAs\xcc\x81oka,\x1fcKing of Magadha,\x1fdca. 274-232 B.C.\x1e'],
        ['00\x1faA\xe2soka,\x1fcKing of Magadha,\x1fdfl. 259 B.C.\x1e', '30\x1faMaurya dynasty.\x1e'],
        ['04\x1faAsoka,\x1fcKing of Magadha,\x1fdca. 274-232 B.C.\x1e'],
        ['00\x1faA\xe2soka,\x1fcKing of Magadha,\x1fdfl. 259 B.C\x1e', '30\x1faMaurya dynasty\x1e'],
        ['00\x1faAs\xcc\x81oka,\x1fcKing of Magadha,\x1fdfl. 259 B.C.\x1e', '30\x1faMaurya family.\x1e']
    ]
    a, b = read_people(lines)
    print a
    # (('a', u'Asoka'), ('c', u'King of Magadha'), ('d', u'fl. 259 B.C..')): 1
    assert a == {
        (('a', u'A\u015boka'), ('c', u'King of Magadha'), ('d', u'fl. 259 B.C.')): 7,
        (('a', u'Maurya dynasty'),): 2,
        (('a', u'Maurya family'),): 2,
        (('a', u'Asoka'), ('c', u'King of Magadha'), ('d', u'ca. 274-232 B.C.')): 1
    }

def test_name_lookup():
    lines = [
        ['10\x1faBellini, Giovanni,\x1fd1516.\x1e'],
        ['10\x1faBellini, Giovanni,\x1fdd. 1516\x1e']
    ]
    a, b = read_people(lines)
    assert a == {(('a', 'Bellini, Giovanni'), ('d', 'd. 1516')): 2}
    assert b == {((u'a', u'Bellini, Giovanni'), (u'd', u'1516')): ((u'a', u'Bellini, Giovanni'), (u'd', u'd. 1516'))}

def test_cleopatra():
    return
    lines = [
        ['00\x1faCleopatra,\x1fcQueen of Egypt,\x1fdd. 30 B.C\x1fxFiction.\x1e'],
        ['00\x1faCleopatra,\x1fcQueen of Egypt,\x1fdd. 30 B.C.\x1fxFiction\x1e'],
        [' 0\x1faCleopatra, Queen of Egypt, d. 30 B.C.\x1fxFiction.\x1e'],
        ['00\x1faCleopatra,\x1fcQueen of Egypt,\x1fdd. 30 B.C.\x1fxFiction\x1e'],
        ['00\x1faCleopatra,\x1fcqueen of Egypt,\x1fdd. B.C. 30\x1fxFiction\x1e'],
        ['00\x1faCleopatra,\x1fcQueen of Egypt,\x1fdd. 30 B.C.\x1fxFiction\x1e'],
        ['00\x1faCleopatra,\x1fcQueen of Egypt,\x1fdd. 30 B.C.\x1fvFiction.\x1e'],
        ['00\x1faCleopatra,\x1fcQueen of Egypt,\x1fdd. 30 B.C.\x1fxFiction.\x1e']
    ]
    a, b = read_people(lines)
    assert a == {
        (('a', u'Cleopatra'), ('c', u'Queen of Egypt'), ('d', u'd. 30 B.C.')): 8,
    }

def test_date_field_missing():
    lines = [[' 0\x1faMoore, Henry Spencer, 1898-\x1e']]
    a, b = read_people(lines)
    assert a == {
        (('a', u'Moore, Henry Spencer'), ('d', u'1898-')): 1
    }
    assert b == {}

def test_numbers_in_name():
    lines = [
        [' 0\x1faFielding, Henry, 1707-1754.  The history of the adventures of Joseph Andrews.\x1e'],
        ['14\x1faFielding, Henry,\x1fd1707-1754.\x1ftJoseph Andrews.\x1e'],
        ['10\x1faFielding, Henry,\x1fd1707-1754.\x1ftHistory of the adventures of Joseph Andrews.\x1e'],
        ['14\x1faFielding, Henry,\x1fd1707-1754.\x1ftJoseph Andrews.\x1e'],
        ['10\x1faFielding, Henry,\x1fd1707-1754.\x1ftHistory of the adventures of Joseph Andrews.\x1e'],
        ['10\x1faFielding, Henry,\x1fd1707-1754.\x1ftHistory of the adventures of Joseph Andrews.\x1e'],
        ['10\x1faFielding, Henry,\x1fd1707-1754.\x1ftHistory of the adventures of Joseph Andrews\x1e']
    ]
    a, b = read_people(lines)
    assert a == {
        (('a', u'Fielding, Henry'), ('d', u'1707-1754')): 7
    }

def test_caesar():
    lines = [
        ['10\x1faCaesar, Julius.\x1e'],
        ['14\x1faCaesar, Julius,\x1fd100 B.C.-44B.C.\x1e'],
        ['14\x1faCaesar, Julius,\x1fd100 B.C.-44 B.C.\x1e'],
        ['10\x1faCaesar, Julius\x1e'],
        ['14\x1faCaesar, Julius,\x1fd100 B.C.-44 B.C.\x1e']
    ]
    a, b = read_people(lines)
    assert a == {(('a', 'Caesar, Julius'), ('d', '100 B.C.-44 B.C.')): 5}

def test_salvador_dali():
    lines = [
        ['14\x1faDali\xcc\x81, Salvador,\x1fd1904-1989\x1fvCatalogs.\x1e'],
        ['10\x1faDali, Salvador,\x1fd1904-\x1e'],
        ['10\x1faDal\xe2i, Salvador,\x1fd1904-\x1e'],
        ['10\x1faDal\xe2i, Salvador,\x1fd1904-\x1e'],
        ['10\x1faDal\xe2i, Salvador,\x1fd1904-\x1fxCatalogs.\x1e', '10\x1faMorse, Albert Reynolds,\x1fd1914-\x1fxArt collections\x1fxCatalogs.\x1e'],
        ['10\x1faDal\xe2i, Salvador\x1fy1904-\x1e'],
        ['14\x1faDali\xcc\x81, Salvador,\x1fd1904- \x1fvexhibitions.\x1e'],
        ['14\x1faDali\xcc\x81, Salvador,\x1fd1904- \x1fvexhibitions.\x1e']
    ]
    a, b = read_people(lines)
    assert a == {
        ((u'a', u'Dal\xed, Salvador'), (u'd', u'1904-1989')): 8,
        ((u'a', u'Morse, Albert Reynolds'), (u'd', u'1914-')): 1
    }

def test_date_in_y():
    lines = [
        ['10\x1faShakespeare, William,\x1fd1564-1616\x1fxStage history\x1fy1800-1950.\x1e'],
        ['10\x1faShakespeare, William,\x1fd1564-1616\x1fxStage history\x1fy1800-\x1e'],
        ['10\x1faShakespeare, William,\x1fd1564-1616.\x1e'],
        ['10\x1faShakespeare, William,\x1fd1564-1616\x1fxDramatic production\x1e']
    ]
    a, b = read_people(lines)
    assert a == {((u'a', u'Shakespeare, William'), (u'd', u'1564-1616')): 4}

def test_subtags_swapped():
    lines = [
        ['20\x1faCompton-Burnett, I.\x1fq(Ivy),\x1fd1884-1969.\x1e'],
        ['10\x1faCompton-Burnett, I.\x1fd(Ivy),\x1fq1884-1969\x1fxCriticism and interpretation.\x1e'],
        ['20\x1faCompton-Burnett, I.\x1fq(Ivy),\x1fd1884-1969.\x1e'],
        ['14\x1faCompton-Burnett, I.\x1fq(Ivy),\x1fd1884-1969.\x1e'],
        ['20\x1faCompton-Burnett, I.\x1fq(Ivy),\x1fd1884-1969\x1fxCriticism and interpretation.\x1e'],
        ['20\x1faCompton-Burnett, I.\x1fq(Ivy),\x1fd1884-1969\x1fxCriticism and interpretation.\x1e'],
        ['20\x1faCompton-Burnett, I.\x1fq(Ivy),\x1fd1884-1969\x1fxCriticism and interpretation.\x1e'],
        ['14\x1faCompton-Burnett, I.\x1fq(Ivy),\x1fd1884-1969.\x1e']
    ]
    a, b = read_people(lines)
    assert a == {((u'a', u'Compton-Burnett, I.'), (u'q', u'(Ivy),'), (u'd', u'1884-1969')): 8}

def test():
    lines = [
        [
            '10\x1faWashington, George,\x1fd1732-1799\x1fxFamily\x1fvJuvenile fiction.\x1e',
            '10\x1faJudge, Oney\x1fvJuvenile fiction.\x1e',
            '11\x1faWashington, George,\x1fd1732-1799\x1fxFamily\x1fxFiction.\x1e',
            '11\x1faJudge, Oney\x1fvFiction.\x1e'
        ], [
            '10\x1faJudge, Oney\x1fvJuvenile fiction.\x1e',
            '10\x1faWashington, George,\x1fd1732-1799\x1fxFamily\x1fvJuvenile fiction.\x1e',
            '11\x1faJudge, Oney\x1fvFiction.\x1e',
            '11\x1faWashington, George,\x1fc1732-1799\x1fxFamily\x1fvFiction.\x1e'
        ]
    ]

    a, b = read_people(lines)
    assert a == {((u'a', u'Judge, Oney'),): 4, ((u'a', u'Washington, George'), (u'd', u'1732-1799')): 4}

#    lines = [
#        [' 0\x1faHadrian, Emperor of Rome, 76-138\x1fxFiction.\x1e'],
#        ['00\x1faHadrianus,\x1fcEmperor of Rome,\x1fd76-138\x1fxFiction.\x1e']
#    ]
#    lines = [[' 0\x1faGreene, Graham, 1904- .  The basement room. 1971.\x1e']]

#    lines = [
#        [' 0\x1faGyllembourg-Ehrensvard, Thomasine Christine Buntzen, 1773-1856. To tidsaldre.\x1e'],
#        ['10\x1faGyllembourg, Thomasine,\x1fd1773-1856.\x1ftTo tidsaldre.\x1e'],
#        ['14\x1faGyllembourg-Ehrensva\xcc\x88rd, Thomasine.\x1ftTo tidsaldre.\x1e']
#    ]

#    lines = [['10\x1faClifford, Henry de Clifford, 14th lord,\x1fd1455?-1523\x1fxFiction.\x1e',]]

def test_same_name_different_dates():
    lines = [
        ['10\x1faStrauss, Johann,\x1fd1825-1899.\x1e', '10\x1faStrauss, Johann,\x1fd1804-1849.\x1e'], 
        ['10\x1faStrauss, Johann,\x1fd1825-1899.\x1e', '10\x1faStrauss, Johann,\x1fd1804-1849.\x1e'], 
        ['10\x1faStrauss, Johann,\x1fd1825-1899.\x1e', '10\x1faStrauss, Johann,\x1fd1804-1849.\x1e']
    ]
    a, b = read_people(lines)
    assert a == {
        ((u'a', u'Strauss, Johann'), (u'd', u'1804-1849')): 3,
        ((u'a', u'Strauss, Johann'), (u'd', u'1825-1899')): 3
    }

def test_king_richard_iii():
    lines = [
        ['00\x1faRichard\x1fbIII,\x1fcKing of England,\x1fd1452-1485\x1fvDrama.\x1e'],
        ['00\x1faRichard\x1fbIII,\x1fcKing of England,\x1fd1425-1485\x1fvDrama.\x1e'],
        ['00\x1faRichard\x1fbIII,\x1fcKing of England,\x1fd1452-1485\x1fvDrama.\x1e'],
        ['00\x1faRichard\x1fbIII,\x1fcKing of England,\x1fd1452-1485\x1fvDrama.\x1e'],
        ['00\x1faRichard\x1fbIII,\x1fcKing of England,\x1fd1452-1485\x1fvDrama.\x1e'],
        ['10\x1faShakespeare, William,\x1fd1564-1616.\x1ftKing Richard III.\x1e', '00\x1faRichard\x1fbIII,\x1fcKing of England,\x1fd1452-1485\x1fvDrama.\x1e'],
        ['00\x1faRichard\x1fbIII,\x1fcKing of England,\x1fd1452-1485\x1fxDrama\x1e'],
        ['00\x1faRichard\x1fbIII,\x1fcKing of England,\x1fd1452-1485\x1fvDrama.\x1e'],
        ['00\x1faRichard\x1fbIII,\x1fcKing of England,\x1fd1452-1485\x1fxDrama\x1e'],
        ['04\x1faRichard\x1fbIII,\x1fcKing of England\x1fxDrama.\x1e'],
        ['00\x1faRichard\x1fbIII,\x1fcKing of England,\x1fd1452-1485\x1fxDrama.\x1e'],
        ['00\x1faRichard\x1fbIII,\x1fcKing of England,\x1fd1452-1485\x1fxDrama\x1e'],
        ['10\x1faRichard\x1fbIII,\x1fcKing of England,\x1fd1452-1485\x1fxDrama.\x1e'],
        ['00\x1faRichard\x1fbIII,\x1fcKing of England,\x1fd1452-1485\x1fvDrama.\x1e']
    ]
    a, b = read_people(lines)
    assert a == {
        ((u'a', u'Richard'), (u'b', u'III'), (u'c', u'King of England'), (u'd', u'1452-1485')): 14,
        ((u'a', u'Shakespeare, William'), (u'd', u'1564-1616')): 1
    }

def test_churchill_family():
    lines = [
        ['30\x1faChurchill family\x1e'],
        ['30\x1faChurchill family.\x1e'],
        ['34\x1faChurchill,\x1fcfamily.\x1e'],
        ['30\x1faChurchill family\x1e'],
        ['34\x1faChurchill,\x1fcFamily.\x1e']
    ]
    a, b = read_people(lines)
    assert a == { (('a', 'Churchill family'),): 5}

def test_william_thompson():
    lines = [
        ['10\x1faHodgskin, Thomas,\x1fd1787-1869.\x1e', '10\x1faThompson, William,\x1fd1785?-1833.\x1e'],
        ['10\x1faHodgskin, Thomas,\x1fd1787-1869.\x1e', '10\x1faThompson, William,\x1fd1775-1833.\x1e'],
        ['10\x1faHodgskin, Thomas,\x1fd1787-1869.\x1e', '10\x1faThompson, William,\x1fd1775-1833.\x1e']
    ]
    a, b = read_people(lines)
    assert a == { # better if we could merge the William Thompson subjects
        ((u'a', u'Hodgskin, Thomas'), (u'd', u'1787-1869')): 3,
        ((u'a', u'Thompson, William'), (u'd', u'1775-1833')): 2,
        ((u'a', u'Thompson, William'), (u'd', u'1785?-1833')): 1
    }

def test_marcus_porcius():
    lines = [
        ['10\x1faCato, Marcus Porcius,\x1fd95-46 B.C.\x1fxDrama.\x1e'],
        ['10\x1faCato, Marcus Porcius,\x1fd95-46 B.C.\x1fxDrama\x1e'],
        ['10\x1faCato, Marcus Porcius,\x1fd95-46 B.C.\x1fxDrama.\x1e'],
        ['10\x1faCato, Marcus Porcius,\x1fd95-46 B.C.\x1fxDrama.\x1e'],
        ['10\x1faCato, Marcus Porcius,\x1fd95-46 B.C.\x1fvDrama.\x1e'],
        ['10\x1faCato, Marcus Porcius,\x1fd234-149 B.C.\x1fvDrama.\x1e'],
        ['10\x1faCato, Marcus Porcius,\x1fd95-46 B.C.\x1fxDrama\x1fxEarly works to 1800\x1e']
    ]
    a, b = read_people(lines)
    assert a == {
        ((u'a', u'Cato, Marcus Porcius'), (u'd', u'234-149 B.C.')): 1,
        ((u'a', u'Cato, Marcus Porcius'), (u'd', u'95-46 B.C.')): 6
    }
