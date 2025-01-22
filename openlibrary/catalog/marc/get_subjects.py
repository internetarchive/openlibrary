import re
from collections import defaultdict

from openlibrary.catalog.utils import flip_name, remove_trailing_dot

re_flip_name = re.compile('^(.+), ([A-Z].+)$')

# 'Rhodes, Dan (Fictitious character)'
re_fictitious_character = re.compile(r'^(.+), (.+)( \(.* character\))$')
re_etc = re.compile('^(.+?)[, .]+etc[, .]?$', re.I)
re_comma = re.compile('^([A-Z])([A-Za-z ]+?) *, ([A-Z][A-Z a-z]+)$')

re_place_comma = re.compile('^(.+), (.+)$')
re_paren = re.compile('[()]')


def flip_place(s: str) -> str:
    s = remove_trailing_dot(s).strip()
    # Whitechapel (London, England)
    # East End (London, England)
    # Whitechapel (Londres, Inglaterra)
    if re_paren.search(s):
        return s
    if m := re_place_comma.match(s):
        return f'{m.group(2)} {m.group(1)}'.strip()
    return s


def flip_subject(s: str) -> str:
    if m := re_comma.match(s):
        return m.group(3) + ' ' + m.group(1).lower() + m.group(2)
    else:
        return s


def tidy_subject(s: str) -> str:
    s = remove_trailing_dot(s.strip()).strip()
    if len(s) > 1:
        s = s[0].upper() + s[1:]
    if m := re_etc.search(s):
        return m.group(1)
    if m := re_fictitious_character.match(s):
        return f'{m.group(2)} {m.group(1)}{m.group(3)}'
    if m := re_comma.match(s):
        return f'{m.group(3)} {m.group(1)}{m.group(2)}'
    return s


def four_types(i):
    want = {'subject', 'time', 'place', 'person'}
    ret = {k: i[k] for k in want if k in i}
    for j in (j for j in i if j not in want):
        for k, v in i[j].items():
            if 'subject' in ret:
                ret['subject'][k] = ret['subject'].get(k, 0) + v
            else:
                ret['subject'] = {k: v}
    return ret


def read_subjects(rec):
    subject_fields = {'600', '610', '611', '630', '648', '650', '651', '662'}
    subjects = defaultdict(lambda: defaultdict(int))
    # {'subject': defaultdict(<class 'int'>, {'Japanese tea ceremony': 1, 'Book reviews': 1})}
    for tag, field in rec.read_fields(subject_fields):
        if tag == '600':  # people
            name_and_date = []
            for k, v in field.get_subfields('abcd'):
                v = '(' + v.strip('.() ') + ')' if k == 'd' else v.strip(' /,;:')
                if k == 'a' and re_flip_name.match(v):
                    v = flip_name(v)
                name_and_date.append(v)
            if name := remove_trailing_dot(' '.join(name_and_date)).strip():
                subjects['person'][name] += 1
        elif tag == '610':  # org
            if v := tidy_subject(' '.join(field.get_subfield_values('abcd'))):
                subjects['org'][v] += 1
        elif tag == '611':  # Meeting Name (event)
            v = ' '.join(
                j.strip() for i, j in field.get_all_subfields() if i not in 'vxyz'
            )
            subjects['event'][tidy_subject(v)] += 1
        elif tag == '630':  # Uniform Title (work)
            for v in field.get_subfield_values('a'):
                subjects['work'][tidy_subject(v)] += 1
        elif tag == '650':  # Topical Term (subject)
            for v in field.get_subfield_values('a'):
                subjects['subject'][tidy_subject(v)] += 1
        elif tag == '651':  # Geographical Name (place)
            for v in field.get_subfield_values('a'):
                subjects['place'][flip_place(v)] += 1

        for v in field.get_subfield_values('vx'):  # Form and General subdivisions
            subjects['subject'][tidy_subject(v)] += 1
        for v in field.get_subfield_values('y'):  # Chronological subdivision
            subjects['time'][tidy_subject(v)] += 1
        for v in field.get_subfield_values('z'):  # Geographic subdivision
            subjects['place'][flip_place(v)] += 1
    return {k: dict(v) for k, v in subjects.items()}


def subjects_for_work(rec):
    field_map = {
        'subject': 'subjects',
        'place': 'subject_places',
        'time': 'subject_times',
        'person': 'subject_people',
    }
    subjects = four_types(read_subjects(rec))
    return {field_map[k]: list(v) for k, v in subjects.items()}
