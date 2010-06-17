import re
from openlibrary.catalog.utils import pick_first_date, tidy_isbn, flip_name, remove_trailing_dot
from collections import defaultdict

re_question = re.compile('^\?+$')
re_lccn = re.compile('(...\d+).*')
re_letters = re.compile('[A-Za-z]')
re_oclc = re.compile('^\(OCoLC\).*?0*(\d+)')
re_ocolc = re.compile('^ocolc *$', re.I)
re_ocn_or_ocm = re.compile('^oc[nm](\d+) *$')
re_int = re.compile ('\d{2,}')
re_number_dot = re.compile('\d{3,}\.$')
re_bracket_field = re.compile('^\s*(\[.*\])\.?\s*$')

want = [
    '001',
    '003', # for OCLC
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
    ] + [str(i) for i in range(500,600)] + [ # notes + toc + description
    #'600', '610', '611', '630', '648', '650', '651', '662', # subjects
    '700', '710', '711', # contributions
    '246', '730', '740', # other titles
    '852', # location
    '856'] # URL

class BadMARC(Exception):
    pass

class SeaAlsoAsTitle(Exception):
    pass

def read_lccn(rec):
    fields = rec.get_fields('010')
    if not fields:
        return

    found = []
    for f in fields:
        for k, v in f.get_subfields(['a']):
            lccn = v.strip()
            if re_question.match(lccn):
                continue
            m = re_lccn.search(lccn)
            if not m:
                continue
            lccn = re_letters.sub('', m.group(1)).strip()
            if lccn:
                found.append(lccn)

    return found

def remove_duplicates(seq):
    u = []
    for x in seq:
        if x not in u:
            u.append(x)
    return u

def read_oclc(rec):
    found = []
    tag_001 = rec.get_fields('001')
    tag_003 = rec.get_fields('003')
    if tag_001 and tag_003 and re_ocolc.match(tag_003[0]):
        oclc = tag_001[0]
        m = re_ocn_or_ocm.match(oclc)
        if m:
            oclc = m.group(1)
        assert oclc.isdigit()
        found.append(oclc)

    for f in rec.get_fields('035'):
        for k, v in f.get_subfields(['a']):
            m = re_oclc.match(v)
            if m:
                oclc = m.group(1)
                if oclc not in found:
                    found.append(oclc)
    return remove_duplicates(found)

def read_lc_classification(rec):
    fields = rec.get_fields('050')
    if not fields:
        return

    found = []
    for f in fields:
        contents = f.get_contents(['a', 'b'])
        if 'b' in contents:
            b = ' '.join(contents['b'])
            if 'a' in contents:
                found += [' '.join([a, b]) for a in contents['a']]
            else:
                found += [b]
        # http://openlibrary.org/show-marc/marc_university_of_toronto/uoft.marc:671135731:596
        elif 'a' in contents:
            found += contents['a']
    return found

def read_isbn(rec):
    fields = rec.get_fields('020')
    if not fields:
        return

    found = []
    for f in fields:
        isbn = rec.read_isbn(f)
        if isbn:
            found += isbn
    ret = {}
    seen = set()

    for i in tidy_isbn(found):
        if i in seen: # avoid dups
            continue
        seen.add(i)
        if len(i) == 13:
            ret.setdefault('isbn_13', []).append(i)
        elif len(i) <= 16:
            ret.setdefault('isbn_10', []).append(i)
    return ret

def read_dewey(rec):
    fields = rec.get_fields('082')
    if not fields:
        return
    found = []
    for f in fields:
        found += f.get_subfield_values(['a'])
    return found

def read_work_titles(rec):
    found = []
    tag_240 = rec.get_fields('240')
    if tag_240:
        for f in tag_240:
            title = f.get_subfield_values(['a', 'm', 'n', 'p', 'r'])
            found.append(' '.join(title))

    tag_130 = rec.get_fields('130')
    if tag_130:
        for f in tag_130:
            found.append(' '.join(f.get_lower_subfields()))

    return found

def read_title(rec):
    fields = rec.get_fields('245')
    if not fields:
        raise NoTitle

#   example MARC record with multiple titles:
#   http://openlibrary.org/show-marc/marc_western_washington_univ/wwu_bibs.mrc_revrev.mrc:299505697:862
    contents = fields[0].get_contents(['a', 'b', 'c', 'h'])

    ret = {}
    title = None

#   MARC record with 245a missing:
#   http://openlibrary.org/show-marc/marc_western_washington_univ/wwu_bibs.mrc_revrev.mrc:516779055:1304
    if 'a' in contents:
        title = ' '.join(x.strip(' /,;:') for x in contents['a'])
    elif 'b' in contents:
        title = contents['b'][0].strip(' /,;:')
        del contents['b'][0]
    if title in ('See.', 'See also.'):
        raise SeeAlsoAsTitle
    ret['title'] = title
    if 'b' in contents and contents['b']:
        ret["subtitle"] = ' : '.join([x.strip(' /,;:') for x in contents['b']])
    if 'c' in contents:
        ret["by_statement"] = ' '.join(contents['c'])
    if 'h' in contents:
        h = ' '.join(contents['h']).strip(' ')
        m = re_bracket_field.match(h)
        if m:
            h = m.group(1)
        ret["physical_format"] = h
    return ret

def read_edition_name(rec):
    fields = rec.get_fields('250')
    if not fields:
        return
    found = []
    for f in fields:
        found += [v for k, v in f.get_all_subfields()]
    return found

def read_publisher(rec):
    fields = rec.get_fields('260')
    if not fields:
        return
    publisher = []
    publish_places = []
    for f in fields:
        contents = f.get_contents(['a', 'b'])
        if 'b' in contents:
            publisher += [x.strip(" /,;:") for x in contents['b']]
        if 'a' in contents:
            publish_places += [x.strip(" /.,;:") for x in contents['a'] if x]
    edition = {}
    if publisher:
        edition["publishers"] = publisher
    if len(publish_places) and publish_places[0]:
        edition["publish_places"] = publish_places
    return edition

def read_author_person(f):
    author = {}
    contents = f.get_contents(['a', 'b', 'c', 'd'])
    if 'a' not in contents and 'c' not in contents:
        return # should at least be a name or title
    name = [v.strip(' /,;:') for v in f.get_subfield_values(['a', 'b', 'c'])]
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

def read_author(rec):
    found = []
    count = 0
    fields_100 = rec.get_fields('100')
    fields_110 = rec.get_fields('110')
    fields_111 = rec.get_fields('111')
    count = len(fields_100) + len(fields_110) + len(fields_111)
    if count == 0:
        return
    assert count == 1
    if fields_100:
        return read_author_person(fields_100[0])
    if fields_110:
        f = fields_110[0]
        name = [v.strip(' /,;:') for v in f.get_subfield_values(['a', 'b'])]
        return { 'entity_type': 'org', 'name': ' '.join(name) }
    if fields_111:
        f = fields_111[0]
        name = [v.strip(' /,;:') for v in f.get_subfield_values(['a', 'c', 'd', 'n'])]
        return { 'entity_type': 'event', 'name': ' '.join(name) }

# no monograph should be longer than 50,000 pages
max_number_of_pages = 50000

def read_pagination(rec):
    fields = rec.get_fields('300')
    if not fields:
        return

    pagination = []
    edition = {}
    for f in fields:
        pagination += f.get_subfield_values(['a'])
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

def read_series(rec):
    found = []
    for tag in ('440', '490', '830'):
        fields = rec.get_fields(tag)
        if not fields:
            continue
        for f in fields:
            this = []
            for k, v in f.get_subfields(['a', 'v']):
                if k == 'v' and v:
                    this.append(v)
                    continue
                v = v.rstrip('.,; ')
                if v:
                    this.append(v)
            if this:
                found += [' -- '.join(this)]
    return found

def read_notes(rec):
    found = []
    for tag in range(500,600):
        if tag in (505, 520):
            continue
        fields = rec.get_fields(str(tag))
        if not fields:
            continue
        for f in fields:
            x = f.get_lower_subfields()
            if x:
                found.append(' '.join(x).strip(' '))
    if found:
        return '\n\n'.join(found)

def read_description(rec):
    fields = rec.get_fields('520')
    if not fields:
        return
    found = []
    for f in fields:
        this = f.get_subfield_values(['a'])
        if len(this) != 1:
            print `fields`
            print `line`
            print len(this)
        # multiple 'a' subfields
        # marc_loc_updates/v37.i47.records.utf8:5325207:1062
        # 520: $aManpower policy;$aNusa Tenggara Barat Province
        found += this
    if found:
        return "\n\n".join(found).strip(' ')

def read_url(rec):
    found = []
    for f in rec.get_fields('856'):
        contents = f.get_contents(['3', 'u'])
        if not contents.get('u', []):
            #print `f.ind1(), f.ind2()`, list(f.get_all_subfields())
            continue
        assert len(contents['u']) == 1
        link = { 'url': contents['u'][0].strip(' ') }
        if '3' in contents:
            assert len(contents['3']) == 1
            link['title'] = contents['3'][0].strip(' ')
        found.append(link)
    return found

def read_other_titles(rec):
    return [' '.join(f.get_subfield_values(['a'])) for f in rec.get_fields('246')] \
        + [' '.join(f.get_lower_subfields()) for f in rec.get_fields('730')] \
        + [' '.join(f.get_subfield_values(['a', 'p', 'n'])) for f in rec.get_fields('740')]

def read_location(rec):
    fields = rec.get_fields('852')
    if not fields:
        return
    found = []
    for f in fields:
        found += [v for v in f.get_subfield_values(['a']) if v]
    return found

def read_contributions(rec):
    want = [
        ('700', 'abcde'),
        ('710', 'ab'),
        ('711', 'acdn'),
    ]

    found = []
    for tag, sub in want:
        found += [' '.join(f.get_subfield_values(sub)) for f in rec.get_fields(tag)]
    return found

def read_toc(rec):
    fields = rec.get_fields('505')

    toc = []
    for f in fields:
        toc_line = []
        for k, v in f.get_all_subfields():
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
                else:
                    toc_line = [v.strip('/')]
                continue
            toc_line.append(v.strip(' -'))
        if toc_line:
            toc.append('-- '.join(toc_line))
    found = []
    for i in toc:
        if len(i) > 2048:
            i = i.split('  ')
            found.extend(i)
        else:
            found.append(i)
    return [{'title': i, 'type': '/type/toc_item'} for i in found]

def update_edition(rec, edition, func, field):
    v = func(rec)
    if v:
        edition[field] = v

def read_edition(rec):
    rec.build_fields(want)
    edition = {}
    tag_008 = rec.get_fields('008')
    if len(tag_008) != 1:
        raise BadMARC("single '008' field required")

    f = tag_008[0]
    if not f:
        raise BadMARC("'008' field must not be blank")
    publish_date = str(f)[7:11]

    if publish_date.isdigit() and publish_date != '0000':
        edition["publish_date"] = publish_date
    if str(f)[6] == 't':
        edition["copyright_date"] = str(f)[11:15]
    publish_country = str(f)[15:18]
    if publish_country not in ('|||', '   '):
        edition["publish_country"] = publish_country
    lang = str(f)[35:38]
    if lang not in ('   ', '|||'):
        edition["languages"] = [{ 'key': '/l/' + lang }]

    update_edition(rec, edition, read_lccn, 'lccn')
    update_edition(rec, edition, read_oclc, 'oclc_number')
    update_edition(rec, edition, read_lc_classification, 'lc_classification')
    update_edition(rec, edition, read_dewey, 'dewey_decimal_class')
    update_edition(rec, edition, read_work_titles, 'work_titles')
    update_edition(rec, edition, read_other_titles, 'other_titles')
    update_edition(rec, edition, read_edition_name, 'edition_name')
    update_edition(rec, edition, read_series, 'series')
    update_edition(rec, edition, read_notes, 'notes')
    update_edition(rec, edition, read_description, 'description')
    update_edition(rec, edition, read_location, 'location')
    update_edition(rec, edition, read_contributions, 'contributions')
    update_edition(rec, edition, read_toc, 'table_of_contents')
    update_edition(rec, edition, read_url, 'links')

    v = read_author(rec)
    if v:
        edition['authors'] = [v]

    edition.update(read_subjects(rec))
    edition.update(read_title(rec))

    for func in (read_publisher, read_isbn, read_pagination):
        v = func(rec)
        if v:
            edition.update(v)

    return edition
