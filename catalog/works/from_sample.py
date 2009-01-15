import web, re, sys, codecs
from catalog.marc.fast_parse import *
from catalog.utils import pick_first_date
from pprint import pprint
import catalog.marc.new_parser as parser

sys.stdout = codecs.getwriter('utf-8')(sys.stdout)

re_recording = re.compile('\x1f(hsound ?record|[hn] ?\[\[?(sound|video|phonodisc))', re.I)
re_end_dot = re.compile('[^ ][^ ]\.$', re.UNICODE)
re_marc_name = re.compile('^(.*), (.*)$')

authors = {}
family_names = {}
by_author = {}
by_contrib = {}

def remove_trailing_dot(s):
    m = re_end_dot.search(s)
    if m:
        s = s[:-1]
    return s

def strip_q(q):
    if q.endswith(').'):
        q = q[:-1]
    q = q.strip(' ()/,;:')
    return q

def read(data):
    want = ['008', '041', '100', '110', '111', '130', '240', '245', '500', '700', '710', '711']
    fields = get_tag_lines(data, ['006', '008', '245', '260'] + want)
    seen_008 = False
    found = []
    for tag, line in fields:
        if tag in want:
            found.append((tag, line))
        if tag == '006':
            if line[0] == 'm': # don't want electronic resources
                return (fields, None)
            continue
        if tag == '008':
            if seen_008: # dup
                return (fields, None)
            seen_008 = True
            continue
        if tag in ('240', '245', '260'):
            if re_recording.search(line): # sound recording
                return (fields, None)
            continue
    return (fields, found)

def initials(s):
    return [i[0] for i in s.split(' ')]

def parse_person(line):
    contents = get_person_content(line)
    marc_orig = list(get_all_subfields(line)),
    if not ('a' in contents or 'c' in contents):
        return marc_orig, {}
    assert 'a' in contents or 'c' in contents

    if 'd' in contents:
        author = pick_first_date(contents['d'])
    else:
        author = {}
    #author['marc_orig'] = list(get_all_subfields(line)),
    for tag, f in [ ('b', 'numeration'), ('c', 'title') ]:
        if tag in contents:
            author[f] = ' '.join(x.strip(' /,;:') for x in contents[tag])

    if 'a' in contents:
        name = ' '.join(x.strip(' /,;:') for x in contents['a'])
        name = remove_trailing_dot(name)
        m = re_marc_name.match(name)
        if m:
            author['family_name'] = m.group(1)
            author['given_names'] = m.group(2)
            author['name'] = m.group(2) + ' ' + m.group(1)
        else:
            author['name'] = name
    name_subfields = get_subfield_values(line, ['a', 'b', 'c'])
    author['sort'] = ' '.join(v.strip(' /,;:') for v in name_subfields)


    if 'q' in contents:
        if len(contents['q']) != 1:
            print marc_orig
        assert len(contents['q']) == 1
        q = strip_q(contents['q'][0])
        if 'given_names' in authors:
            assert initials(q) == initials(author['given_names']) \
                    or q.startswith(author['given_names'])
        author['given_names'] = q
    return marc_orig, author

def test_parse_person():
    line = '1 \x1faMoeran, E. J.\x1fq(Ernest John)\x1fq(1894-1950)\x1e'
    person = ([('a', u'Moeran, E. J.'), ('q', u'(Ernest John)'), ('q', u'(1894-1950)')],)
    parse_person(line)

#test_parse_person()

def full_title(line):
    title = ' '.join(v for k, v in line if k in ('a', 'b')).strip(' /,;:')
    return remove_trailing_dot(title)

def test_strip_q():
    for i in ['(%s),', '(%s)', '(%s,']:
        k = i % ('foo')
        j = strip_q(k)
        print k, j
        assert j == 'foo'

    name = 'John X.'
    assert name == strip_q('(%s)' % name)

def print_author(a):
    for k in ('name', 'sort', 'numeration', 'title', 'given_names', 'family_name', 'birth_date', 'death_date'):
        print "%12s: %s" % (k, author.get(k, ''))


def person_as_tuple(p):
    return tuple(p.get(i, None) for i in ('sort', 'birth_date', 'death_date'))

def family_name(a):
    if 'family_name' not in a:
        return
    this = a['family_name']
    family_names.setdefault(this, {})
    as_tuple = tuple(a.get(i, None) for i in ('sort', 'birth_date', 'death_date'))
    as_tuple = person_as_tuple(a)
    family_names[this][as_tuple] = family_names[this].get(as_tuple, 0) + 1

interested = set(['Rowling', 'Shakespeare', 'Sagan', 'Darwin', 'Verne', 'Beckett', 'Churchill', 'Dickens', 'Twain', 'Doyle'])
sorted_interest = sorted(interested)

def edition_list(l):
    for e in l:
        print e['loc']
        for k in sorted((k for k in e.keys() if k.isdigit()), key=int):
            if k == '245':
                t = ' '.join(v.strip(' /,;:') for k, v in e[k][0] if k == 'a')
                title = remove_trailing_dot(t)
                full = full_title(e[k][0])
                print '     title:', title
                if title != full:
                    print 'full title:', full
            print '    ', k, e[k]
        print '---'

def print_interest():
    for k in sorted_interest:
        if k not in family_names:
            continue
        print k
        for a in sorted(family_names[k].keys()):
            if family_names[k][a] > 5:
                print "  %3d %s" % (family_names[k][a], a)
                if a in by_author:
                    print "  by: "
                    for i in sorted(by_author[a].keys()):
                        print ' WORK: %s (%d)' % (i, len(by_author[a][i]))
                        edition_list(by_author[a][i])
#                if a in by_contrib:
#                    print "  contrib: "
#                    edition_list(by_contrib[a])
    print

def work_title(edition):
    if '240' in edition:
        t = ' '.join(v for k, v in edition['240'][0] if k in ('a', 'm', 'n', 'p', 'r'))
    else:
        t = ' '.join(v.strip(' /,;:') for k, v in edition['245'][0] if k == 'a')
    return remove_trailing_dot(t)

#for line in open(sys.argv[1]):
for line in sys.stdin:
    loc, data = eval(line)
    (orig_fields, fields) = read(data)
    if not fields:
        continue
    new_interest = False
    edition = {}
    for tag, l in fields:
        #if tag in ('100', '700'):
        if tag == '100':
            try:
                marc, person = parse_person(l)
            except:
                print loc
                raise
            if not person:
                continue
            #print author['marc_orig']
#            print marc
            if person.get('family_name', None) in interested:
#                family_name(person)
                new_interest = True
#            print_author(author)
            continue
            tag_map = { '100': 'authors', '700': 'contribs' }
            person['marc'] = marc
            edition.setdefault(tag_map[tag], []).append(person)
        continue
        if tag == '008':
            lang = str(l)[35:38]
            edition['lang'] = lang
            continue
        edition.setdefault(tag, []).append(list(get_all_subfields(line)))
    #for k in sorted(family_names.keys()):

    if new_interest:
        edition['loc'] = loc
        print (loc, data)
        continue
        title = work_title(edition)
#        rec = parser.read_edition(loc, data)
        for p in edition.get('authors', []):
            a = by_author.setdefault(person_as_tuple(p), {})
            a.setdefault(title, []).append(edition)
#        for p in edition.get('contribs', []):
#            by_contrib.setdefault(person_as_tuple(p), []).append(edition)
for k, v in by_author.items():
    print (k, v)
#print_interest()

