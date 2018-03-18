import re, urllib2
from openlibrary.catalog.marc.fast_parse import get_tag_lines, get_all_subfields, get_subfield_values, get_subfields, BadDictionary
from openlibrary.catalog.utils import remove_trailing_dot, remove_trailing_number_dot, flip_name
from openlibrary.catalog.importer.db_read import get_mc
from collections import defaultdict

subject_fields = set(['600', '610', '611', '630', '648', '650', '651', '662'])

re_large_book = re.compile('large.*book', re.I)

re_edition_key = re.compile(r'^/(?:b|books)/(OL\d+M)$')

re_ia_marc = re.compile('^(?:.*/)?([^/]+)_(marc\.xml|meta\.mrc)(:0:\d+)?$')
def get_marc_source(w):
    found = set()
    for e in w['editions']:
        sr = e.get('source_records', [])
        if sr:
            found.update(i[5:] for i in sr if i.startswith('marc:'))
        else:
            m = re_edition_key.match(e['key'])
            if not m:
                print e['key']
            mc = get_mc('/b/' + m.group(1))
            if mc and not mc.startswith('amazon:') and not re_ia_marc.match(mc):
                found.add(mc)
    return found

def get_marc_subjects(w):
    for src in get_marc_source(w):
        data = None
        from openlibrary.catalog.get_ia import get_data
        try:
            data = get_data(src)
        except ValueError:
            print 'bad record source:', src
            print 'http://openlibrary.org' + w['key']
            continue
        except urllib2.HTTPError, error:
            print 'HTTP error:', error.code, error.msg
            print 'http://openlibrary.org' + w['key']
        if not data:
            continue
        try:
            lines = list(get_tag_lines(data, subject_fields))
        except BadDictionary:
            print 'bad dictionary:', src
            print 'http://openlibrary.org' + w['key']
            continue
        if lines:
            yield lines

re_place_comma = re.compile('^(.+), (.+)$')
re_paren = re.compile('[()]')
def flip_place(s):
    s = remove_trailing_dot(s)
    # Whitechapel (London, England)
    # East End (London, England)
    # Whitechapel (Londres, Inglaterra)
    if re_paren.search(s):
        return s
    m = re_place_comma.match(s)
    return m.group(2) + ' ' + m.group(1) if m else s

# 'Rhodes, Dan (Fictitious character)'
re_fictitious_character = re.compile('^(.+), (.+)( \(.* character\))$')
re_etc = re.compile('^(.+?)[, .]+etc[, .]?$', re.I)
re_aspects = re.compile(' [Aa]spects$')
re_comma = re.compile('^([A-Z])([A-Za-z ]+?) *, ([A-Z][A-Z a-z]+)$')

def tidy_subject(s):
    s = s.strip()
    if len(s) < 2:
        print('short subject:', repr(s))
    else:
        s = s[0].upper() + s[1:]
    m = re_etc.search(s)
    if m:
        return m.group(1)
    s = remove_trailing_dot(s)
    m = re_fictitious_character.match(s)
    if m:
        return m.group(2) + ' ' + m.group(1) + m.group(3)
    m = re_comma.match(s)
    if m:
        return m.group(3) + ' ' + m.group(1) + m.group(2)
    return s

def flip_subject(s):
    m = re_comma.match(s)
    if m:
        return m.group(3) + ' ' + m.group(1).lower()+m.group(2)
    else:
        return s

def find_aspects(line):
    cur = [(i, j) for i, j in get_subfields(line, 'ax')]
    if len(cur) < 2 or cur[0][0] != 'a' or cur[1][0] != 'x':
        return
    a, x = cur[0][1], cur[1][1]
    x = x.strip('. ')
    a = a.strip('. ')
    if not re_aspects.search(x):
        return
    if a == 'Body, Human':
        a = 'the Human body'
    return x + ' of ' + flip_subject(a)

# 'Ram Singh, guru of Kuka Sikhs'
re_flip_name = re.compile('^(.+), ([A-Z].+)$')

def find_subjects(marc_subjects):
    person = defaultdict(int)
    event = defaultdict(int)
    work = defaultdict(int)
    org = defaultdict(int)
    time = defaultdict(int)
    place = defaultdict(int)
    subject = defaultdict(int)
    #fiction = False
    for lines in marc_subjects:
        for tag, line in lines:
            aspects = find_aspects(line)
            if aspects:
                subject[aspects] += 1
            if re_large_book.search(line):
                continue
            if tag == '600': # people
                name_and_date = []
                for k, v in get_subfields(line, ['a', 'b', 'c', 'd']):
                    v = '(' + v.strip('.() ') + ')' if k == 'd' else v.strip(' /,;:')
                    if k == 'a':
                        if v == 'Mao, Zedong':
                            v = 'Mao Zedong'
                        else:
                            m = re_flip_name.match(v)
                            if m:
                                v = flip_name(v)
                    name_and_date.append(v)
                name = remove_trailing_dot(' '.join(name_and_date)).strip()
                if name != '':
                    person[name] += 1
            elif tag == '610': # org
                v = ' '.join(get_subfield_values(line, 'abcd'))
                v = v.strip()
                if v:
                    v = remove_trailing_dot(v).strip()
                if v:
                    v = tidy_subject(v)
                if v:
                    org[v] += 1

                for v in get_subfield_values(line, 'a'):
                    v = v.strip()
                    if v:
                        v = remove_trailing_dot(v).strip()
                    if v:
                        v = tidy_subject(v)
                    if v:
                        org[v] += 1
            elif tag == '611': # event
                v = ' '.join(j.strip() for i, j in get_all_subfields(line) if i not in 'vxyz')
                if v:
                    v = v.strip()
                v = tidy_subject(v)
                if v:
                    event[v] += 1
            elif tag == '630': # work
                for v in get_subfield_values(line, ['a']):
                    v = v.strip()
                    if v:
                        v = remove_trailing_dot(v).strip()
                    if v:
                        v = tidy_subject(v)
                    if v:
                        work[v] += 1
            elif tag == '650': # topical
                for v in get_subfield_values(line, ['a']):
                    if v:
                        v = v.strip()
                    v = tidy_subject(v)
                    if v:
                        subject[v] += 1
            elif tag == '651': # geo
                for v in get_subfield_values(line, ['a']):
                    if v:
                        place[flip_place(v).strip()] += 1
            else:
                print 'other', tag, list(get_all_subfields(line))

            cur = [v for k, v in get_all_subfields(line) if k=='a' or v.strip('. ').lower() == 'fiction']

            # skip: 'Good, Sally (Fictitious character) in fiction'
            if len(cur) > 1 and cur[-1].strip('. ').lower() == 'fiction' and ')' not in cur[-2]:
                subject[flip_subject(cur[-2]) + ' in fiction'] += 1

            for v in get_subfield_values(line, ['y']):
                v = v.strip()
                if v:
                    time[remove_trailing_dot(v).strip()] += 1
            for v in get_subfield_values(line, ['v']):
                v = v.strip()
                if v:
                    v = remove_trailing_dot(v).strip()
                v = tidy_subject(v)
                if v:
                    subject[v] += 1
            for v in get_subfield_values(line, ['z']):
                v = v.strip()
                if v:
                    place[flip_place(v).strip()] += 1
            for v in get_subfield_values(line, ['x']):
                v = v.strip()
                if not v:
                    continue
                if aspects and re_aspects.search(v):
                    continue
                v = tidy_subject(v)
                if v:
                    subject[v] += 1

            v_and_x = get_subfield_values(line, ['v', 'x'])
            #if 'Fiction' in v_and_x or 'Fiction.' in v_and_x:
            #    fiction = True
    #if 'Fiction' in subject:
    #    del subject['Fiction']
    ret = {}
    if person:
        ret['person'] = dict(person)
    if time:
        ret['time'] = dict(time)
    if place:
        ret['place'] = dict(place)
    if subject:
        ret['subject'] = dict(subject)
    if event:
        ret['event'] = dict(event)
    if org:
        ret['org'] = dict(org)
    if work:
        ret['work'] = dict(work)
    return ret

def four_types(i):
    want = set(['subject', 'time', 'place', 'person'])
    ret = dict((k, i[k]) for k in want if k in i)
    for j in (j for j in i.keys() if j not in want):
        for k, v in i[j].items():
            if 'subject' in ret:
                ret['subject'][k] = ret['subject'].get(k, 0) + v
            else:
                ret['subject'] = {k: v}
    return ret

