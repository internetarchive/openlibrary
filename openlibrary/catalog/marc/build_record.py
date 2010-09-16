from fast_parse import *
from warnings import warn
from openlibrary.catalog.utils import pick_first_date
import re

re_question = re.compile('^\?+$')
re_lccn = re.compile('(...\d+).*')
re_letters = re.compile('[A-Za-z]')
re_isbn = re.compile('([^ ()]+[\dX])(?: \((?:v\. (\d+)(?: : )?)?(.*)\))?')
re_oclc = re.compile ('^\(OCoLC\).*?0*(\d+)')
re_int = re.compile ('\d{2,}')
re_number_dot = re.compile('\d{3,}\.$')

re_translation1 = re.compile(r'^(.{,6})\btranslation of\b', re.I)
re_translation2 = re.compile(r'^([\'"]?).*?\btranslation of\b[ :,;]*(.*)\1', re.I)

# no monograph should be longer than 50,000 pages
max_number_of_pages = 50000

want = [
    '001',
    '008', # publish date, country and language
    '010', # lccn
    '020', # isbn
    '035', # oclc
    '050', # lc classification
    '082', # dewey
    '100', '110', '111', # authors TODO
    '130', '240', # work title
    '245', # title
    '250', # edition
    '260', # publisher
    '300', # pagination
    '440', '490', '830' # series
    ] + map(str, range(500,590)) + [ # notes + toc + description
    '600', '610', '630', '650', '651', # subjects + genre
    '700', '710', '711', # contributions
    '246', '730', '740', # other titles
    '852', # location
    '856' # URL
]

re_series = re.compile('^(.*) series$', re.I)

def read_lccn(fields):
    if '010' not in fields:
        return {}

    found = []
    for line in fields['010']:
        for k, v in get_subfields(line, ['a']):
            lccn = v.strip()
            if re_question.match(lccn):
                continue
            m = re_lccn.search(lccn)
            if not m:
                continue
            lccn = re_letters.sub('', m.group(1)).strip()
            if lccn:
                found.append(lccn)

    return {'lccn': found}

def read_isbn(fields):
    if '020' not in fields:
        return {}

    found = []
    for line in fields['020']:
        if line.find('\x1f') != -1:
            for k, v in get_subfields(line, ['a', 'z']):
                m = re_isbn.match(v)
                if m:
                    found.append(m.group(1))
        else:
            m = re_isbn.match(line[3:-1])
            if m:
                found.append(m.group(1))
    ret = {}
    for i in found:
        i = i.replace('-', '')
        if len(i) == 13:
            ret.setdefault('isbn_13', []).append(i)
        else:
            ret.setdefault('isbn_10', []).append(i)

    return ret

def read_oclc(fields):
    if '035' not in fields:
        return {}

    found = []
    for line in fields['035']:
        for v in get_subfield_values(line, ['a']):
            m = re_oclc.match(v)
            if not m:
                continue
            oclc = m.group(1)
            if oclc not in found:
                found.append(oclc)
    return {'oclc_number': found } if found else {}

def read_author_person(line):
    author = {}
    contents = get_contents(line, ['a', 'b', 'c', 'd'])
    if 'a' not in contents and 'c' not in contents:
        return None # should at least be a name or title
    name = [v.strip(' /,;:') for v in get_subfield_values(line, ['a', 'b', 'c'])]
    if 'd' in contents:
        author = pick_first_date(contents['d'])
        if 'death_date' in author and author['death_date']:
            death_date = author['death_date']
            if re_number_dot.search(death_date):
                author['death_date'] = death_date[:-1]

    author['name'] = ' '.join(name)
    author['entity_type'] = 'person'
    subfields = [
        ('a', 'personal_name'),
        ('b', 'numeration'),
        ('c', 'title')
    ]
    for subfield, field_name in subfields:
        if subfield in contents:
            author[field_name] = ' '.join([x.strip(' /,;:') for x in contents[subfield]])
    if 'q' in contents:
        author['fuller_name'] = ' '.join(contents['q'])
    return author

def read_authors(fields):
    found = []
    author = [tag for tag in fields if tag in ('100', '110', '111')]
    if len(author) == 0:
        return {}
    if len(author) != 1:
        for tag in ('100', '110', '111'):
            print tag, fields[tag]
    assert len(author) == 1
    if '100' in fields:
        line = fields['100'][0]
        author = read_author_person(line)
    if '110' in fields:
        line = fields['110'][0]
        name = [v.strip(' /,;:') for v in get_subfield_values(line, ['a', 'b'])]
        author = { 'entity_type': 'org', 'name': ' '.join(name) }
    if '111' in fields:
        line = fields['111'][0]
        name = [v.strip(' /,;:') for v in get_subfield_values(line, ['a', 'c', 'd', 'n'])]
        author = { 'entity_type': 'event', 'name': ' '.join(name) }

    return {'authors': [author]} if author else {}

def read_title(fields):
    if '245' not in fields:
        return {}

#   example MARC record with multiple titles:
#   http://openlibrary.org/show-marc/marc_western_washington_univ/wwu_bibs.mrc_revrev.mrc:299505697:862
#   assert len(fields['245']) == 1
    line = fields['245'][0]
    contents = get_contents(line, ['a', 'b', 'c', 'h'])

    edition = {}
    title = None
#   MARC record with 245a missing:
#   http://openlibrary.org/show-marc/marc_western_washington_univ/wwu_bibs.mrc_revrev.mrc:516779055:1304
    if 'a' in contents:
        title = ' '.join(x.strip(' /,;:') for x in contents['a'])
    elif 'b' in contents: # handle broken records
        title = contents['b'][0].strip(' /,;:')
        del contents['b'][0]
    edition['title'] = title
    if 'b' in contents and contents['b']:
        edition["subtitle"] = ' : '.join([x.strip(' /,;:') for x in contents['b']])
    if 'c' in contents:
        edition["by_statement"] = ' '.join(contents['c'])
    if 'h' in contents:
        edition["physical_format"] = ' '.join(contents['h'])
    return edition

def read_lc_classification(fields):
    if '050' not in fields:
        return {}

    found = []
    for line in fields['050']:
        contents = get_contents(line, ['a', 'b'])
        if 'b' in contents:
            b = ' '.join(contents['b'])
            if 'a' in contents:
                found += [' '.join([a, b]) for a in contents['a']]
            else:
                found += [b]
        # http://openlibrary.org/show-marc/marc_university_of_toronto/uoft.marc:671135731:596
        elif 'a' in contents:
            found += contents['a']
    if found:
        return {'lc_classifications': [i.strip() for i in found]}
    else:
        return {}

def read_dewey(fields):
    if '082' not in fields:
        return {}
    found = []
    for line in fields['082']:
        found += get_subfield_values(line, ['a'])
    return {'dewey_decimal_class': found }

def join_subfield_values(line, subfields):
    return ' '.join(get_subfield_values(line, subfields))

def read_work_titles(fields):
    found = []
    if '240' in fields:
        for line in fields['240']:
            title = join_subfield_values(line, ['a', 'm', 'n', 'p', 'r'])
            if title not in found:
                found.append(title)

    if '130' in fields:
        for line in fields['130']:
            title = ' '.join(get_lower_subfields(line))
            if title not in found:
                found.append(title)

    return { 'work_titles': found } if found else {}

def read_edition_name(fields):
    if '250' not in fields:
        return {}
    found = []
    for line in fields['250']:
        found += [v for k, v in get_all_subfields(line)]
    return {'edition_name': ' '.join(found)}

def read_publisher(fields):
    if '260' not in fields:
        return {}
    publisher = []
    publish_place = []
    for line in fields['260']:
        contents = get_contents(line, ['a', 'b'])
        if 'b' in contents:
            publisher += [x.strip(" /,;:") for x in contents['b']]
        if 'a' in contents:
            publish_place += [x.strip(" /.,;:") for x in contents['a']]
    edition = {}
    if publisher:
        edition["publishers"] = publisher
    if publish_place:
        edition["publish_places"] = publish_place
    return edition

def read_pagination(fields):
    if '300' not in fields:
        return {}

    pagination = []
    edition = {}
    for line in fields['300']:
        pagination += get_subfield_values(line, ['a'])
    if pagination:
        edition["pagination"] = ' '.join(pagination)
        num = [] # http://openlibrary.org/show-marc/marc_university_of_toronto/uoft.marc:2617696:825
        for x in pagination:
            num += [ int(i) for i in re_int.findall(x.replace(',',''))]
            num += [ int(i) for i in re_int.findall(x) ]
        valid = [i for i in num if i < max_number_of_pages]
        if valid:
            edition["number_of_pages"] = max(valid)
    return edition

def read_series(fields):
    found = []
    for tag in ('440', '490', '830'):
        if tag not in fields:
            continue
        for line in fields[tag]:
            this = []
            for k, v in get_subfields(line, ['a', 'v']):
                if k == 'v' and v:
                    this.append(v)
                    continue
                v = v.rstrip('.,; ')
                m = re_series.match(v)
                if m:
                    v = m.group(1)
                if v:
                    this.append(v)
            if this:
                s = ' -- '.join(this)
                if s not in found:
                    found.append(s)
    return {'series': found} if found else {}
                
def read_contributions(fields):
    want = [
        ('700', 'abcde'),
        ('710', 'ab'),
        ('711', 'acdn'),
    ]

    found = []
    for tag, subfields in want:
        if tag not in fields:
            continue
        for line in fields[tag]:
            found.append(join_subfield_values(line, subfields))
    return { 'contributions': found } if found else {}

def remove_duplicates(seq):
    u = []
    for x in seq:
        if x not in u:
            u.append(x)
    return u

def read_subjects(fields):
    want = [
        ('600', 'abcd'),
        ('610', 'ab'),
        ('630', 'acdegnpqst'),
        ('650', 'a'),
        ('651', 'a'),
    ]

    found = []
    subdivision = ['v', 'x', 'y', 'z']

    for tag, subfields in want:
        if tag not in fields:
            continue
        for line in fields[tag]:
            a = get_subfield_values(line, subdivision)
            b = " -- ".join(get_subfield_values(line, subfields) + a)
            found.append(b)
    
    return {'subjects': found} if found else {}
    
def read_genres(fields):
    found = []
    for tag in '600', '650', '651':
        if tag not in fields:
            continue
        for line in fields[tag]:
            found += get_subfield_values(line, ['v'])
    return { 'genres': remove_duplicates(found) } if found else {}

def read_translation(fields):
    tag = '500'
    if tag not in fields:
        return {}
    for line in fields[tag]:
        for value in get_subfield_values(line, ['a']):
            value = value.strip()
            if not re_translation1.match(value):
                continue
            if value.startswith("Translation of the author's thesis"):
                continue # not interested
            m = re_translation2.match(value)
            return { 'translation_of': m.group(2) }
    return {}

def read_notes(fields):
    found = []
    for tag in range(500,590):
        if tag in (505, 520) or str(tag) not in fields:
            continue
        tag = str(tag)
        for line in fields[tag]:
            try:
                x = get_lower_subfields(line)
            except IndexError:
                print `line`
                raise
            if x:
                found.append(' '.join(x))
    return {'notes': '\n\n'.join(found)} if found else {}

def read_toc(fields):
    if '505' not in fields:
        return {}

    toc = []
    for line in fields['505']:
        toc_line = []
        for k, v in get_all_subfields(line):
            if k == 'a':
                toc_split = [i.strip() for i in v.split('--')]
                if any(len(i) > 2048 for i in toc_split):
                    toc_split = [i.strip() for i in v.split(' - ')]
                # http://openlibrary.org/show-marc/marc_miami_univ_ohio/allbibs0036.out:3918815:7321
                if any(len(i) > 2048 for i in toc_split):
                    toc_split = [i.strip() for i in v.split('; ')]
                # FIXME:
                # http://openlibrary.org/show-marc/marc_western_washington_univ/wwu_bibs.mrc_revrev.mrc:938969487:3862
                if any(len(i) > 2048 for i in toc_split):
                    toc_split = [i.strip() for i in v.split(' / ')]
                assert isinstance(toc_split, list)
                toc.extend(toc_split)
                continue
            if k == 't':
                if toc_line:
                    toc.append(' -- '.join(toc_line))
                if (len(v) > 2048):
                    toc_line = [i.strip() for i in v.strip('/').split('--')]
                continue
            toc_line.append(v.strip(' -'))
        if toc_line:
            toc.append('-- '.join(toc_line))
    if not toc:
        return {}
    found = []
    for i in toc:
        if len(i) > 2048:
            i = i.split('  ')
            found.extend(i)
        else:
            found.append(i)
    return { 'table_of_contents': found }

def read_description(fields):
    if '520' not in fields:
        return {}
    found = []
    wrap = False
    for line in fields['520']:
        this = get_subfield_values(line, ['a'])
        if len(this) != 1:
#            print `fields['520']`
#            print `line`
            print len(this)
        assert len(this) == 1
        found += this
        if line[-3:-1] == '++':
            wrap = True
        else:
            wrap = False
    return {'description': "\n\n".join(found) } if found else {}

def read_other_titles(fields):
    found = []
    
    if '246' in fields:
        for line in fields['246']:
            title = join_subfield_values(line, ['a'])
            if title not in found:
                found.append(title)

    if '730' in fields:
        for line in fields['730']:
            title = ' '.join(get_lower_subfields(line))
            if title not in found:
                found.append(title)

    if '740' in fields:
        for line in fields['740']:
            title = join_subfield_values(line, ['a', 'p', 'n'])
            if title not in found:
                found.append(title)

    return {"other_titles": found} if found else {}

def read_location(fields):
    if '852' not in fields:
        return {}
    found = []
    for line in fields['852']:
        found += [v for v in get_subfield_values(line, ['a']) if v]
    return { 'location': found } if found else {}

def read_url(fields):
    if '856' not in fields:
        return {}
    found = []
    for line in fields['856']:
        found += get_subfield_values(line, ['u'])
    return { 'uri': found } if found else {}

def build_record(data):
    fields = {}
    for tag, line in handle_wrapped_lines(get_tag_lines(data, want)):
        fields.setdefault(tag, []).append(line)

    edition = {}
    if len(fields['008']) != 1:
        warn("There should be a single '008' field.")
        return {}
    f = fields['008'][0]
    publish_date = str(f)[7:11]
    if publish_date.isdigit():
        edition["publish_date"] = publish_date
    publish_country = str(f)[15:18]
    if publish_country not in ('|||', '   '):
        edition["publish_country"] = publish_country
    lang = str(f)[35:38]
    if lang not in ('   ', '|||'):
        edition["languages"] = [{ 'key': '/l/' + lang }]
    edition.update(read_lccn(fields))
    edition.update(read_isbn(fields))
    edition.update(read_oclc(fields))
    edition.update(read_lc_classification(fields))
    edition.update(read_dewey(fields))
    edition.update(read_authors(fields))
    edition.update(read_title(fields))
    edition.update(read_genres(fields))
    edition.update(read_subjects(fields))
    edition.update(read_pagination(fields))
    edition.update(read_series(fields))
    edition.update(read_work_titles(fields))
    edition.update(read_other_titles(fields))
    edition.update(read_edition_name(fields))
    edition.update(read_publisher(fields))
    edition.update(read_contributions(fields))
    edition.update(read_location(fields))
    edition.update(read_url(fields))
    edition.update(read_toc(fields))
    edition.update(read_notes(fields))
    edition.update(read_translation(fields))
    edition.update(read_description(fields))
    return edition

def test_candide_by_voltaire():
    bpl = open('test_data/bpl_0486266893').read()
    lc = open('test_data/lc_1416500308').read()

    fields = {}
    want = [ '41', '490', '830' ]
    for tag, line in handle_wrapped_lines(get_tag_lines(lc, want)):
        fields.setdefault(tag, []).append(line)
    assert read_series(fields) == {'series': [u'Enriched classics']}

    fields = {}
    want = [ '41', '490', '830' ]
    for tag, line in handle_wrapped_lines(get_tag_lines(bpl, want)):
        fields.setdefault(tag, []).append(line)
    assert read_series(fields) == {'series': [u'Dover thrift editions']}
