import web, re, codecs, sys
from time import time
from catalog.marc.fast_parse import get_subfields, get_all_subfields, get_subfield_values
from catalog.utils import pick_first_date
from unicodedata import normalize
from pprint import pprint

sys.stdout = codecs.getwriter('utf-8')(sys.stdout)

# bad cats:
# ... animal births
# ... animal deaths
# ... peoples

db = web.database(dbn='postgres', db='wiki_people')
db.printing = False

re_comma = re.compile(', *')

re_marc_name = re.compile('^(.*), (.*)$')

def flip_name(name):
    m = re_marc_name.match(name)
    if m:
        return m.group(2) + ' ' + m.group(1)
    return name

re_title_of = re.compile('^(.*) (of .*)$')

re_digit = re.compile('\d+')
re_decade = re.compile('^(\d+)s$')
re_bc_date = re.compile('^(.*) B\.C\.?$')
re_cent = re.compile('^(?:fl\.? ?)?(\d+)[a-z]{0,2}\.? cent\.$')
# fl. 13th cent/14th cent.
re_cent_range = re.compile('^(?:fl\.? ?)?(\d+)[a-z]{0,2}\.?(?: cent)?[-/](\d+)[a-z]{0,2}\.? cent\.$')
re_century = re.compile('^(\d+)[a-z][a-z] century$')

def decade_match(a, start, ca):
    end = start + 10
    if ca:
        start -= 9
        end += 9
    if a.isdigit():
        return start <= int(a) < end
    return any((start <= int(c) < end) for c in re_digit.findall(a))

def year_approx_match(a, b): 
    approx_century_match = False
    if a.startswith('ca. '):
        ca = True
        a = a[4:]
        range = 15
    else:
        ca = False
        range = 9
    if a == b:
        return True
    if a.replace('.', '') == b:
        return True # ca. 440 B.C.
    if a.endswith(' cent.') and b.endswith(' century') and b.startswith(a[:-1]):
        return True

    bc = False
    if b.endswith(' BC'):
        m = re_bc_date.match(a)
        if m:
            a = m.group(1)
            b = b[:-3]
            bc = True
    if approx_century_match and a.isdigit() and b.endswith(' century'):
        a = int(a)
        m = re_century.match(b)
        assert m
        cent = int(m.group(1))
        start = cent - 1 if not bc else cent
        end = cent if not bc else cent + 1
        if start * 100 <= a < end * 100:
            return True

    if b.isdigit():
        b = int(b)
        if a.isdigit() and (bc or b < 1850) and abs(int(a) - b) <= range:
            return True
        if approx_century_match and a.endswith(' cent.'):
            m = re_cent.match(a)
            if m:
                cent = int(m.group(1))
                start = cent - 1 if not bc else cent
                end = cent if not bc else cent + 1
                if start * 100 <= b < end * 100:
                    return True
        for c in re_digit.findall(a):
            c = int(c)
            if c == b:
                return True
            if (bc or b < 1850) and abs(c - b) <= range:
                return True
        return False
    m = re_decade.match(b)
    if not m:
        return False
    start = int(m.group(1))
    return decade_match(a, start, ca)

def test_year_approx_match():
    assert not year_approx_match('1939', '1940')
    assert year_approx_match('582', '6th century')
    assert year_approx_match('13th cent.', '1240')
    assert year_approx_match('ca. 360 B.C.', '365 BC')
    assert year_approx_match('1889', '1890')
    assert year_approx_match('1883?', '1882')
    assert year_approx_match('1328?', '1320s')
    assert year_approx_match('11th cent.', '11th century')
    assert not year_approx_match('1330', '1320s')
    assert not year_approx_match('245 B.C.', '3rd century BC')

#test_year_approx_match()

# fl. 13th cent/14th cent.
def cent_range(c):
    m = re_cent_range.match(c)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        assert b == a + 1
        return ((a-1) * 100, b * 100)
    m = re_cent.match(c)
    assert m
    a = int(m.group(1))
    return ((a-1) * 100, a * 100)

re_fl = re.compile('^fl\.? ?(\d+)\.?$')

def get_birth_and_death(cats):
    birth = None
    death = None
    for c in cats:
        if c.endswith(' births'):
            birth = c[:-7]
            continue
        elif c.endswith(' deaths'):
            death = c[:-7]
            continue
    return birth, death

re_century_writers_cat = re.compile('(\d+)[a-z]{2}-century.* writers')

def date_match(dates, cats):
    match_found = False
    if len(dates) == 1 and 'date' in dates:
        marc = dates['date']
        if marc.startswith('fl.'):
            m = re_fl.match(marc)
            if m:
                birth, death = get_birth_and_death(cats)
                if birth and death and birth.isdigit() and death.isdigit():
                    return int(birth) < int(m.group(1)) < int(death)
        if marc.endswith(' cent.'):
            m = re_cent.match(marc)
            if m:
                cent = marc[:-6] + '-century'
                if any(c.endswith(' writers') and cent in c for c in cats):
                    return True
            m = re_cent_range.match(marc)
            if m:
                if any(cm.group(1) in m.groups() for cm in (re_century_writers_cat.match(c) for c in cats) if cm):
                    return True

            try:
                (a, b) = cent_range(marc)
            except:
                print marc
                raise
            for c in cats:
                for f in (' births', ' deaths'):
                    if not c.endswith(f):
                        continue
                    date = c[:-len(f)]
                    if date.isdigit():
                        if a < int(date) < b:
                            match_found = True
                        else:
                            return False
                    else:
                        if year_approx_match(marc, date):
                            match_found = True
                        else:
                            return False

        return match_found

    for f in ['birth', 'death']:
        if f + '_date' not in dates:
            continue
        marc = dates[f + '_date']
        this_cats = [i[:-(len(f)+2)] for i in cats if i.endswith(' %ss' % f)]
        if not this_cats:
            continue
        m = any(year_approx_match(marc, i) for i in this_cats)
        if m:
            match_found = True
        else:
            return False
    return match_found

def norm_name(n):
    return re_comma.sub(' ', n).lower()

# example: "Ibn Daud, Abraham ben David," -> "Ibn Daud"
re_name_comma = re.compile('^([^, ]+ [^, ]+)?, [^ ]')

def name_lookup(fields):
    def join_fields(fields, want):
        return ' '.join(v for k, v in fields if k in want)

    fields = [(k, v.lower()) for k, v in fields]

    if not any(k == 'd' for k, v in fields):
        return []
    ab = [v for k, v in fields if k in 'ab']
    name = ' '.join(ab)
    flipped = flip_name(name)
    names = set([name, flipped])

    a = join_fields(fields, 'a')
    m = re_name_comma.match(a)
    if m:
        names.add(m.group(1))

    #names = set([flipped])
    if any(k == 'c' for k, v in fields):
        name = join_fields(fields, 'abc')
        names.update([name, flip_name(name)])
        title = [v for k, v in fields if k in 'c'] 
        names.update([' '.join(title + ab), ' '.join(title + [flipped])])
        title = ' '.join(title)
        names.update(["%s (%s)" % (name, title), "%s (%s)" % (flipped, title)])
        sp = title.find(' ')
        if sp != -1:
            m = re_title_of.search(title)
            if m:
                role, of_place = m.groups()
                names.update([' '.join(ab + [of_place]), ' '.join([flipped, of_place])])
                names.update([' '.join([role] + ab + [of_place]), ' '.join([role, flipped, of_place])])

            t = title[:sp]
            names.update([' '.join([t] + ab), ' '.join([t, flipped])])
        if 'of st. ' in title: # for "Richard of St. Victor"
            names.update([i.replace('of st.', 'of saint') for i in names])

    found = []
    for n in set(re_comma.sub(' ', n) for n in names):
        iter = db.query("select title, cats, name, persondata from names, people where people.id = names.person_id and name=$n", {'n':n})
        x = [(i.title, eval(i.cats), i.name, i.persondata) for i in iter if not i.title.startswith('Personal life of ')]
        found += x
    return found

noble_or_clergy = ['King', 'Queen', 'Prince', 'Princess', 'Duke', 'Archduke', 'Baron', 'Pope', 'Antipope', 'Bishop', 'Archbishop']
re_noble_or_clergy = re.compile('(' + '|'.join( noble_or_clergy ) + ')')

def strip_brackets(line):
    if line[4] == '[' and line[-2] == ']':
        return line[0:4] + line[5:-2] + line[-1]
    else:
        return line

def fmt_line(fields):
    def bold(s):
        return ''.join(i + '\b' + i for i in s)
    def norm(s):
        return normalize('NFC', s)
    return ''.join(bold("$" + k) + norm(v) for k, v in fields)

def pick_from_match(match):
    l = [(norm_name(k), v) for k, v in match.items()]
    good = [(k, v) for k, v in l if any(k == m for m in v['match_name'])]
    if len(good) == 1:
        return dict(good)
    exact_date = [(k, v) for k, v in l if v['exact_dates']]
    if len(exact_date) == 1:
        return dict(exact_date)
    if len(exact_date) > 1 and len(good) > 1:
        exact_date = [(k, v) for k, v in good if v['exact_dates']]
        if len(exact_date) == 1:
            return dict(exact_date)
    return match

def more_than_one_match(match):
    return [("http://en.wikipedia.org/wiki/" + name.replace(' ', '_'), i) for name, i in match.items()]

def test_date_match():
    # $aAngelico,$cfra,$dca. 1400-l455.
    dates = {'birth_date': u'ca. 1400', 'death_date': u'1455'}
    cats = [u'1395 births', u'1455 deaths']
    assert date_match(dates, cats)

    # $aAndocides,$dca. 440-ca. 390 B.C.
    dates = {'birth_date': u'ca. 440 B.C.', 'death_date': u'ca. 390 B.C.'}
    cats = [u'440 BC births', u'390 BC deaths', u'Ancient Athenians']
    assert date_match(dates, cats)

    # $aAlexander,$cof Hales,$dca. 1185-1245.
    dates = {'birth_date': u'ca. 1185', 'death_date': u'1245'}
    cats = [u'13th century philosophers', u'1245 deaths', u'Roman Catholic philosophers', u'English theologians', u'Franciscans', u'Scholastic philosophers', u'People from Gloucestershire']
    assert date_match(dates, cats)

    dates = {'birth_date': u'1922'}
    cats = [u'1830 births', u'1876 deaths']
    assert not date_match(dates, cats)

    dates = {'birth_date': u'1889', 'death_date': u'1947'}
    cats = [u'1890 births', u'1947 deaths']
    assert date_match(dates, cats)

    dates = {'birth_date': u'1889', 'death_date': u'1947'}
    cats = [u'1890 births', u'1947 deaths']
    assert date_match(dates, cats)

    dates = {}
    cats = [u'1890 births', u'1947 deaths']
    assert not date_match(dates, cats)

    dates = {'birth_date': u'1883?', 'death_date': u'1963'}
    cats = [u'1882 births', u'1963 deaths']
    assert date_match(dates, cats)

    dates = {'birth_date': u'1328?', 'death_date': u'1369'}
    cats = [u'Karaite rabbis', u'1320s births', u'1369 deaths']
    assert date_match(dates, cats)

    dates = {'birth_date': u'ca. 1110', 'death_date': u'ca. 1180'}
    cats = [u'1120s births', u'1198 deaths']
    assert date_match(dates, cats)

    # $aAbu Nuwas,$dca. 756-ca. 810.  # Abu Nuwas
    dates = {'birth_date': u'ca. 756', 'death_date': u'ca. 810'}
    cats = [u'750 births', u'810 deaths']
    assert date_match(dates, cats)

date_cats = (' births', ' deaths', 'century writers', 'century Latin writers', 'century women writers', 'century French writers') # time for an regexp

def exact_date_match(dates, cats):
    if 'date' in dates or not all(i in dates for i in ('birth_date', 'death_date')):
        return False
    if any('ca.' in i for i in dates.values()):
        return False
    birth, death = get_birth_and_death(cats)
    return dates['birth_date'] == birth and dates['death_date'] == death

def look_for_match(found, dates, verbose):
    match = {}
    for name, cats, match_name, pd in found:
        found_name_match = norm_name(name) == match_name
        #seen.add(name)
        if not any(any(cat.endswith(i) for i in date_cats) for cat in cats):
            if False and not found_name_match:
                print 'name match, but no date cats'
                print name, cats, match_name
                print dates
                print
            continue
        exact_dm = exact_date_match(dates, cats)
        dm = exact_dm or date_match(dates, cats)
        if not dm and found_name_match:
            if 'death_date' in dates:
                death = dates['death_date']
                if death + ' deaths' in cats:
                    dm = True
            elif 'birth_date' in dates:
                birth = dates['birth_date']
                if birth.isdigit():
                    assert birth + ' births' not in cats
        if dm:
            if name in match:
                match[name]['match_name'].append(match_name)
            else:
                match[name] = {'cats': cats, 'exact_dates': exact_dm, 'match_name': [match_name]}
        if not verbose:
            continue
        print (name, match_name)
        print "cats =", cats
        print ('match' if dm else 'no match')
        for field in ['birth', 'death']:
            print field + 's:', [i[:-(len(field)+2)] for i in cats if i.endswith(' %ss' % field)],
        print
    if verbose:
        print '---'
    return match

def test_lookup():
    line = '00\x1faEgeria,\x1fd4th/5th cent.\x1e' # count=3
    wiki = 'Egeria (pilgrim)'
    print fmt_line(get_subfields(line, 'abcd'))
    fields = tuple((k, v.strip(' /,;:')) for k, v in get_subfields(line, 'abcd'))
    print fields
    found = name_lookup(fields)
    print found
    dates = pick_first_date(v for k, v in fields if k == 'd')
    assert dates.items()[0] != ('date', '')
    print dates
    print
    print look_for_match(found, dates, True)

#test_lookup()

def test_lookup2():
    line = '00\x1faRichard,\x1fcof St. Victor,\x1fdd. 1173.\x1e'
    print fmt_line(get_subfields(line, 'abcd'))
    fields = tuple((k, v.strip(' /,;:')) for k, v in get_subfields(line, 'abcd'))
    print fields
    found = name_lookup(fields)
    dates = pick_first_date(v for k, v in fields if k == 'd')
    assert dates.items()[0] != ('date', '')
    print dates
    print
    match = look_for_match(found, dates, False)
    pprint(match)
    print
    match = pick_from_match(match)
    pprint(match)

def test_lookup3():
    line = '00\x1faJohn,\x1fcof Paris,\x1fd1240?-1306.\x1e'
    print fmt_line(get_subfields(line, 'abcd'))
    fields = tuple((k, v.strip(' /,;:')) for k, v in get_subfields(line, 'abcd'))
    print fields
    found = name_lookup(fields)
#    print [i for i in found if 'Paris' in i[0]]
#    found = [(u'John of Paris', [u'Christian philosophers', u'Dominicans', u'Roman Catholic theologians', u'13th-century Latin writers', u'1255 births', u'1306 deaths'], u'john of paris', None)]
    dates = pick_first_date(v for k, v in fields if k == 'd')
    match = look_for_match(found, dates, False)
    match = pick_from_match(match)
    pprint(match)

def test_lookup4():
    fields = (('a', 'Forbes, George'), ('d', '1849-1936.'))
    found = name_lookup(fields)
    dates = pick_first_date(v for k, v in fields if k == 'd')
    match = look_for_match(found, dates, False)
    for k, v in match.iteritems():
        print k, v
    match = pick_from_match(match)
    pprint(match)

#test_lookup4()

def db_marc_lookup():
    verbose = False
    articles = set()
    count = 0
    count_with_date = 0
    t0 = time()
    match_count = 0
    total = 3596802
    prev_fields = None
    fh = open('matches', 'w')
    bad = codecs.open('more_than_one_match', 'w', 'utf8')
    for line in open('/1/edward/wikipedia/marc_authors2'):
        count+=1
#        (author_count, line) = eval(line)
        (line, author_count) = eval(line)
#        line = strip_brackets(line)
        if count % 5000 == 0:
            t1 = time() - t0
            rec_per_sec = count / t1
            time_left = (total - count) / rec_per_sec
            #print fmt_line(get_subfields(line, 'abcd'))
#            print list(get_subfields(line, 'abcd'))
            print line
            print count, count_with_date, match_count, "%.2f%% %.2f mins left" % (float(match_count * 100.0) / float(count_with_date), time_left / 60)
        fields = tuple((k, v.strip(' /,;:')) for k, v in line)
        if prev_fields == fields:
            continue
        prev_fields = fields
        dates = pick_first_date(v for k, v in fields if k == 'd')
        if dates.items()[0] == ('date', ''):
            continue
        count_with_date += 1
        if verbose:
            print line
            print dates
        is_noble_or_clergy = any(k =='c' and re_noble_or_clergy.search(v) for k, v in fields)
        found = name_lookup(fields)
        if not found:
            continue
            if is_noble_or_clergy:
                print 'noble or clergy not found:', line
                print
            continue
        match = look_for_match(found, dates, verbose)

        if not match:
            continue
            if is_noble_or_clergy:
                print 'noble or clergy not found:'
                print fmt_line(line)
                print found
                print
            continue
        match_count+=1
#        articles.add(match.keys()[0])
        if len(match) != 1:
            match = pick_from_match(match)
        if len(match) != 1:
            print >> bad, "\n" + fmt_line(line)
            for i in more_than_one_match(match):
                print >> bad, i
        else:
            #print (list(get_subfields(line, 'abcd')), match.keys()[0])
            cats = match.values()[0]['cats']
            exact = match.values()[0]['exact_dates']
            dc = [i for i in cats if any(i.endswith(j) for j in date_cats)]
            print >> fh, (match.keys()[0], fields, author_count, dc, exact, 'Living people' in cats)
    print match_count
    fh.close()

if __name__ == '__main__':
    db_marc_lookup()
