import re, urllib2
from openlibrary.catalog.marc.fast_parse import get_tag_lines, get_all_subfields, get_subfield_values, get_subfields, BadDictionary
from openlibrary.catalog.utils import remove_trailing_dot, remove_trailing_number_dot, flip_name
from openlibrary.catalog.get_ia import get_data
from openlibrary.catalog.importer.db_read import get_mc
from collections import defaultdict

subject_fields = set(['600', '610', '611', '630', '648', '650', '651', '662'])

re_large_book = re.compile('large.*book', re.I)

re_ia_marc = re.compile('^(?:.*/)?([^/]+)_(marc\.xml|meta\.mrc)(:0:\d+)?$')
def get_marc_source(w):
    found = set()
    for e in w['editions']:
        sr = e.get('source_record', [])
        if sr:
            found.update(i[5:] for i in sr if i.startswith('marc:'))
        else:
            mc = get_mc(e['key'])
            if mc and not mc.startswith('amazon:') and not re_ia_marc.match(mc):
                found.add(mc)
    return found

def get_marc_subjects(w):
    for src in get_marc_source(w):
        data = None
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

re_comma = re.compile('^(.+), (.+)$')
re_paren = re.compile('[()]')
def flip_place(s):
    s = remove_trailing_dot(s)
    # Whitechapel (London, England)
    # East End (London, England)
    # Whitechapel (Londres, Inglaterra)
    if re_paren.match(s):
        return s
    m = re_comma.match(s)
    return m.group(2) + ' ' + m.group(1) if m else s

# 'Rhodes, Dan (Fictitious character)'
re_fictitious_character = re.compile('^(.+), (.+)( \(.* character\))$')
re_etc = re.compile('^(.+?)[, .]+etc[, .]?$', re.I)

def tidy_subject(s):
    s = s.strip()
    if len(s) < 2:
        print 'short subject:', `s`
    else:
        s = s[0].upper() + s[1:]
    m = re_etc.search(s)
    if m:
        return m.group(1)
    s = remove_trailing_dot(s)
    m = re_fictitious_character.match(s)
    return m.group(2) + ' ' + m.group(1) + m.group(3) if m else s

# 'Ram Singh, guru of Kuka Sikhs'
re_flip_name = re.compile('^(.+), ([A-Z].+)$')

def find_subjects(w, marc_subjects=None):
    people = defaultdict(int)
    genres = defaultdict(int)
    when = defaultdict(int)
    place = defaultdict(int)
    subject = defaultdict(int)
    #fiction = False
    for lines in marc_subjects or get_marc_subjects(w):
        for tag, line in lines:
            if re_large_book.match(line):
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
                    people[name] += 1
            if tag == '650':
                for v in get_subfield_values(line, ['a']):
                    if v:
                        v = v.strip()
                    v = tidy_subject(v)
                    if v:
                        subject[v] += 1
            if tag == '651':
                for v in get_subfield_values(line, ['a']):
                    if v:
                        place[flip_place(v).strip()] += 1

            for v in get_subfield_values(line, ['y']):
                v = v.strip()
                if v:
                    when[remove_trailing_dot(v).strip()] += 1
            for v in get_subfield_values(line, ['v']):
                v = v.strip()
                if v:
                    subject[remove_trailing_dot(v).strip()] += 1
            for v in get_subfield_values(line, ['z']):
                v = v.strip()
                if v:
                    place[flip_place(v).strip()] += 1
            for v in get_subfield_values(line, ['x']):
                v = v.strip()
                if v:
                    v = tidy_subject(v)
                if v:
                    subject[v] += 1

            v_and_x = get_subfield_values(line, ['v', 'x'])
            #if 'Fiction' in v_and_x or 'Fiction.' in v_and_x:
            #    fiction = True
    #if 'Fiction' in subject:
    #    del subject['Fiction']
    ret = {}
    if people:
        ret['people'] = dict(people)
    if when:
        ret['times'] = dict(when)
    if place:
        ret['places'] = dict(place)
    if subject:
        ret['subjects'] = dict(subject)
    return ret

