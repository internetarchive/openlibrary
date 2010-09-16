import re
from openlibrary.catalog.utils import pick_first_date, tidy_isbn, flip_name, remove_trailing_dot, remove_trailing_number_dot
from collections import defaultdict

re_question = re.compile('^\?+$')
re_lccn = re.compile('(...\d+).*')
re_letters = re.compile('[A-Za-z]')
re_oclc = re.compile('^\(OCoLC\).*?0*(\d+)')
re_ocolc = re.compile('^ocolc *$', re.I)
re_ocn_or_ocm = re.compile('^oc[nm]0*(\d+) *$')
re_int = re.compile ('\d{2,}')
re_number_dot = re.compile('\d{3,}\.$')
re_bracket_field = re.compile('^\s*(\[.*\])\.?\s*$')
foc = '[from old catalog]'

def strip_foc(s):
    return s[:-len(foc)].rstrip() if s.endswith(foc) else s

class NoTitle(Exception):
    pass

class SeeAlsoAsTitle(Exception):
    pass

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
    ] + [str(i) for i in range(500,595)] + [ # notes + toc + description
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
        if oclc.isdigit():
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
            found.append(remove_trailing_dot(' '.join(title).strip(',')))

    tag_130 = rec.get_fields('130')
    if tag_130:
        for f in tag_130:
            title = ' '.join(v for k, v in f.get_all_subfields() if k.islower() and k != 'n')
            found.append(remove_trailing_dot(title.strip(',')))

    return remove_duplicates(found)

def read_title(rec):
    fields = rec.get_fields('245')
    if not fields:
        fields = rec.get_fields('740')
    if not fields:
        raise NoTitle

#   example MARC record with multiple titles:
#   http://openlibrary.org/show-marc/marc_western_washington_univ/wwu_bibs.mrc_revrev.mrc:299505697:862
    contents = fields[0].get_contents(['a', 'b', 'c', 'h', 'p'])

    b_and_p = [i for i in fields[0].get_subfield_values(['b', 'p']) if i]

    ret = {}
    title = None

#   MARC record with 245a missing:
#   http://openlibrary.org/show-marc/marc_western_washington_univ/wwu_bibs.mrc_revrev.mrc:516779055:1304
    if 'a' in contents:
        title = ' '.join(x.strip(' /,;:') for x in contents['a'])
    elif b_and_p:
        title = b_and_p.pop(0).strip(' /,;:')
# talis_openlibrary_contribution/talis-openlibrary-contribution.mrc:183427199:255
    if title in ('See.', 'See also.'):
        raise SeeAlsoAsTitle
# talis_openlibrary_contribution/talis-openlibrary-contribution.mrc:5654086:483
# scrapbooksofmoun03tupp
    if title is None:
        subfields = list(fields[0].get_all_subfields())
        title = ' '.join(v for k, v in subfields)
        if not title: # ia:scrapbooksofmoun03tupp
            raise NoTitle
    ret['title'] = remove_trailing_dot(title)
    if b_and_p:
        ret["subtitle"] = ' : '.join(remove_trailing_dot(x.strip(' /,;:')) for x in b_and_p)
    if 'c' in contents:
        ret["by_statement"] = remove_trailing_dot(' '.join(contents['c']))
    if 'h' in contents:
        h = ' '.join(contents['h']).strip(' ')
        m = re_bracket_field.match(h)
        if m:
            h = m.group(1)
        assert h
        ret["physical_format"] = h
    return ret

def read_edition_name(rec):
    fields = rec.get_fields('250')
    if not fields:
        return
    found = []
    for f in fields:
        f.remove_brackets()
        found += [v for k, v in f.get_all_subfields()]
    return ' '.join(found)

lang_map = {
    'ser': 'srp', # http://www.archive.org/details/zadovoljstvauivo00lubb
    'sze': 'slo',
    'fr ': 'fre',
    'fle': 'dut',
}

def read_languages(rec):
    fields = rec.get_fields('041')
    if not fields:
        return
    found = []
    for f in fields:
        found += [i for i in f.get_subfield_values('a') if i and len(i) == 3]
    return [{'key': '/languages/' + lang_map.get(i, i)} for i in found]

def read_pub_date(rec):
    fields = rec.get_fields('260')
    if not fields:
        return
    found = []
    for f in fields:
        found += [i for i in f.get_subfield_values('c') if i]
    return remove_trailing_number_dot(found[0]) if found else None

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
    f.remove_brackets()
    author = {}
    contents = f.get_contents(['a', 'b', 'c', 'd', 'e'])
    if 'a' not in contents and 'c' not in contents:
        return # should at least be a name or title
    name = [v.strip(' /,;:') for v in f.get_subfield_values(['a', 'b', 'c'])]
    if 'd' in contents:
        author = pick_first_date(strip_foc(d).strip(',') for d in contents['d'])
        if 'death_date' in author and author['death_date']:
            death_date = author['death_date']
            if re_number_dot.search(death_date):
                author['death_date'] = death_date[:-1]

    author['name'] = ' '.join(name)
    author['entity_type'] = 'person'
    subfields = [
        ('a', 'personal_name'),
        ('b', 'numeration'),
        ('c', 'title'),
        ('e', 'role')
    ]
    for subfield, field_name in subfields:
        if subfield in contents:
            author[field_name] = remove_trailing_dot(' '.join([x.strip(' /,;:') for x in contents[subfield]]))
    if 'q' in contents:
        author['fuller_name'] = ' '.join(contents['q'])
    for f in 'name', 'personal_name':
        author[f] = remove_trailing_dot(strip_foc(author[f]))
    return author

# 1. if authors in 100, 110, 111 use them
# 2. if first contrib is 710 or 711 use it
# 3. if 

def person_last_name(f):
    v = list(f.get_subfield_values('a'))[0]
    return v[:v.find(', ')] if ', ' in v else v

def last_name_in_245c(rec, person):
    fields = rec.get_fields('245')
    if not fields:
        return
    last_name = person_last_name(person).lower()
    return any(any(last_name in v.lower() for v in f.get_subfield_values(['c'])) for f in fields)

def read_authors(rec):
    count = 0
    fields_100 = rec.get_fields('100')
    fields_110 = rec.get_fields('110')
    fields_111 = rec.get_fields('111')
    count = len(fields_100) + len(fields_110) + len(fields_111)
    if count == 0:
        return
    # talis_openlibrary_contribution/talis-openlibrary-contribution.mrc:11601515:773 has two authors:
    # 100 1  $aDowling, James Walter Frederick.
    # 111 2  $aConference on Civil Engineering Problems Overseas.

    found = [f for f in (read_author_person(f) for f in fields_100) if f]
    for f in fields_110:
        f.remove_brackets()
        name = [v.strip(' /,;:') for v in f.get_subfield_values(['a', 'b'])]
        found.append({ 'entity_type': 'org', 'name': remove_trailing_dot(' '.join(name))})
    for f in fields_111:
        f.remove_brackets()
        name = [v.strip(' /,;:') for v in f.get_subfield_values(['a', 'c', 'd', 'n'])]
        found.append({ 'entity_type': 'event', 'name': remove_trailing_dot(' '.join(name))})
    if found:
        return found

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
    for tag in range(500,595):
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
        this = [i for i in f.get_subfield_values(['a']) if i]
        #if len(this) != 1:
        #    print f.get_all_subfields()
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
        if '3' not in contents:
            found += [{ 'url': u.strip(' ') } for u in contents['u']]
            continue
        assert len(contents['3']) == 1
        title = contents['3'][0].strip(' ')
        found += [{ 'url': u.strip(' '), 'title': title  } for u in contents['u']]

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
    want = dict((
        ('700', 'abcdeq'),
        ('710', 'ab'),
        ('711', 'acdn'),
    ))

    ret = {}
    skip_authors = set()
    for tag in ('100', '110', '111'):
        fields = rec.get_fields(tag)
        for f in fields:
            skip_authors.add(tuple(f.get_all_subfields()))
    
    if not skip_authors:
        for tag, f in rec.read_fields(['700', '710', '711']):
            f = rec.decode_field(f)
            if tag == '700':
                if 'authors' not in ret or last_name_in_245c(rec, f):
                    ret.setdefault('authors', []).append(read_author_person(f))
                    skip_authors.add(tuple(f.get_subfields(want[tag])))
                continue
            elif 'authors' in ret:
                break
            if tag == '710':
                name = [v.strip(' /,;:') for v in f.get_subfield_values(want[tag])]
                ret['authors'] = [{ 'entity_type': 'org', 'name': remove_trailing_dot(' '.join(name))}]
                skip_authors.add(tuple(f.get_subfields(want[tag])))
                break
            if tag == '711':
                name = [v.strip(' /,;:') for v in f.get_subfield_values(want[tag])]
                ret['authors'] = [{ 'entity_type': 'event', 'name': remove_trailing_dot(' '.join(name))}]
                skip_authors.add(tuple(f.get_subfields(want[tag])))
                break

    for tag, f in rec.read_fields(['700', '710', '711']): 
        sub = want[tag]
        cur = tuple(rec.decode_field(f).get_subfields(sub))
        if tuple(cur) in skip_authors:
            continue
        name = remove_trailing_dot(' '.join(strip_foc(i[1]) for i in cur).strip(','))
        ret.setdefault('contributions', []).append(name) # need to add flip_name

    return ret

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

re_bad_char = re.compile(u'[\xa0\xf6]')

def read_edition(rec):
    handle_missing_008=True
    rec.build_fields(want)
    edition = {}
    tag_008 = rec.get_fields('008')
    if len(tag_008) == 0:
        if not handle_missing_008:
            raise BadMARC("single '008' field required")
    if len(tag_008) > 1:
        len_40 = [f for f in tag_008 if len(f) == 40]
        if len_40:
            tag_008 = len_40
        tag_008 = [min(tag_008, key=lambda f:f.count(' '))]
    if len(tag_008) == 1:
        #assert len(tag_008[0]) == 40
        f = re_bad_char.sub(' ', tag_008[0])
        if not f:
            raise BadMARC("'008' field must not be blank")
        publish_date = str(f)[7:11]

        if publish_date.isdigit() and publish_date != '0000':
            edition["publish_date"] = publish_date
        if str(f)[6] == 't':
            edition["copyright_date"] = str(f)[11:15]
        publish_country = str(f)[15:18]
        if publish_country not in ('|||', '   ', '\x01\x01\x01', '???'):
            edition["publish_country"] = publish_country
        lang = str(f)[35:38]
        if lang not in ('   ', '|||', '', '???'):
            edition["languages"] = [{ 'key': '/languages/' + lang }]
    else:
        assert handle_missing_008
        update_edition(rec, edition, read_languages, 'languages')
        update_edition(rec, edition, read_pub_date, 'publish_date')

    update_edition(rec, edition, read_lccn, 'lccn')
    update_edition(rec, edition, read_authors, 'authors')
    update_edition(rec, edition, read_oclc, 'oclc_numbers')
    update_edition(rec, edition, read_lc_classification, 'lc_classifications')
    update_edition(rec, edition, read_dewey, 'dewey_decimal_class')
    update_edition(rec, edition, read_work_titles, 'work_titles')
    update_edition(rec, edition, read_other_titles, 'other_titles')
    update_edition(rec, edition, read_edition_name, 'edition_name')
    update_edition(rec, edition, read_series, 'series')
    update_edition(rec, edition, read_notes, 'notes')
    update_edition(rec, edition, read_description, 'description')
    update_edition(rec, edition, read_location, 'location')
    update_edition(rec, edition, read_toc, 'table_of_contents')
    update_edition(rec, edition, read_url, 'links')

    edition.update(read_contributions(rec))

    try:
        edition.update(read_title(rec))
    except NoTitle:
        if 'work_titles' in edition:
            assert len(edition['work_titles']) == 1
            edition['title'] = edition['work_titles'][0]
            del edition['work_titles']
        else:
            raise

    for func in (read_publisher, read_isbn, read_pagination):
        v = func(rec)
        if v:
            edition.update(v)

    return edition
