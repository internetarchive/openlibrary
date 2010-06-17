from openlibrary.catalog.merge.names import flip_marc_name

import sys, re

# no monograph should be longer than 50,000 pages
max_number_of_pages = 50000
re_isbn = re.compile('([^ ()]+[\dX])(?: \((?:v\. (\d+)(?: : )?)?(.*)\))?')
re_question = re.compile('^\?+$')
re_lccn = re.compile('(...\d+).*')
re_int = re.compile ('\d{2,}')
re_oclc = re.compile ('^\(OCoLC\).*?0*(\d+)')
re_date = map (re.compile, [
    '(?P<birth_date>\d+\??)-(?P<death_date>\d+\??)',
    '(?P<birth_date>\d+\??)-',
    'b\.? (?P<birth_date>(?:ca\. )?\d+\??)',
    'd\.? (?P<death_date>(?:ca\. )?\d+\??)',
    '(?P<birth_date>.*\d+.*)-(?P<death_date>.*\d+.*)',
    '^(?P<birth_date>[^-]*\d+[^-]+ cent\.[^-]*)$'])

re_ad_bc = re.compile(r'\b(B\.C\.?|A\.D\.?)')
re_number_dot = re.compile('\d{3,}\.$')
re_date_fl = re.compile('^fl[., ]')

class BigToc:
    pass

def specific_subtags(f, subtags):
    return [j for i, j in f.subfield_sequence if i in subtags]

def parse_date(date):
    if re_date_fl.match(date):
        return {}
    if date.find('-') == -1:
        for r in re_date:
            m = r.search(date)
            if m:
                return m.groupdict()
        return {}

    parts = date.split('-')
    i = { 'birth_date': parts[0].strip() }
    if len(parts) == 2:
        parts[1] = parts[1].strip()
        if parts[1]:
            i['death_date'] = parts[1]
            if not re_ad_bc.search(i['birth_date']):
                m = re_ad_bc.search(i['death_date'])
                if m:
                    i['birth_date'] += ' ' + m.group(1)
    return i

def remove_trailing_number_dot(date):
    m = re_number_dot.search(date)
    if m:
        return date[:-1]
    else:
        return date

def pick_first_date(dates):
    # this is to handle this case:
    # 100: $aLogan, Olive (Logan), $cSikes, $dMrs., $d1839-
    # see http://archive.org/download/gettheebehindmes00logaiala/gettheebehindmes00logaiala_meta.mrc
    # or http://pharosdb.us.archive.org:9090/show-marc?record=gettheebehindmes00logaiala/gettheebehindmes00logaiala_meta.mrc:0:521

    for date in dates:
        result = parse_date(date)
        if result != {}:
            return result

    return { 'date': ' '.join([remove_trailing_number_dot(d) for d in dates]) }

def find_authors (r, edition):
    authors = []
    for f in r.get_fields('100'):
        author = {}
        if 'a' not in f.contents and 'c' not in f.contents:
            continue # should at least be a name or title
        name = " ".join([j.strip(' /,;:') for i, j in f.subfield_sequence if i in 'abc'])
        if 'd' in f.contents:
            author = pick_first_date(f.contents['d'])
            author['db_name'] = ' '.join([name] + f.contents['d'])
        else:
            author['db_name'] = name
        author['name'] = name
        author['entity_type'] = 'person'
        subfields = [
            ('a', 'personal_name'),
            ('b', 'numeration'),
            ('c', 'title')
        ]
        for subfield, field_name in subfields:
            if subfield in f.contents:
                author[field_name] = ' '.join([x.strip(' /,;:') for x in f.contents[subfield]])
        if 'q' in f.contents:
            author['fuller_name'] = ' '.join(f.contents['q'])
        authors.append(author)

    for f in r.get_fields('110'):
        author = {
            'entity_type': 'org',
            'name': " ".join([j.strip(' /,;:') for i, j in f.subfield_sequence if i in 'ab'])
        }
        author['db_name'] = author['name']
        authors.append(author)

    for f in r.get_fields('111'):
        author = {
            'entity_type': 'event',
            'name': " ".join([j.strip(' /,;:') for i, j in f.subfield_sequence if i in 'acdn'])
        }
        author['db_name'] = author['name']
        authors.append(author)
    if authors:
        edition['authors'] = authors

def find_contributions(r, edition):
    contributions = []
    for tag, subtags in [ ('700', 'abcde'), ('710', 'ab'), ('711', 'acdn') ]:
        for f in r.get_fields(tag):
            contributions.append(" ".join(specific_subtags(f, subtags)))
    if contributions:
        edition['contributions'] = contributions

def find_contributions_complex(r, edition):
    authors = []
    for f in r.get_fields('700'):
        author = {}
        if 'a' not in f.contents and 'c' not in f.contents:
            continue # should at least be a name or title
        name = " ".join([j.strip(' /,;:') for i, j in f.subfield_sequence if i in 'abc'])
        if 'd' in f.contents:
            author = pick_first_date(f.contents['d'])
            author['db_name'] = ' '.join([name] + f.contents['d'])
        else:
            author['db_name'] = name
        author['name'] = name
        author['entity_type'] = 'person'
        subfields = [
            ('a', 'personal_name'),
            ('b', 'numeration'),
            ('c', 'title')
        ]
        for subfield, field_name in subfields:
            if subfield in f.contents:
                author[field_name] = ' '.join([x.strip(' /,;:') for x in f.contents[subfield]])
        if 'q' in f.contents:
            author['fuller_name'] = ' '.join(f.contents['q'])
        authors.append(author)

    for f in r.get_fields('710'):
        author = {
            'entity_type': 'org',
            'name': " ".join([j.strip(' /,;:') for i, j in f.subfield_sequence if i in 'ab'])
        }
        author['db_name'] = author['name']
        authors.append(author)

    for f in r.get_fields('711'):
        author = {
            'entity_type': 'event',
            'name': " ".join([j.strip(' /,;:') for i, j in f.subfield_sequence if i in 'acdn'])
        }
        author['db_name'] = author['name']
        authors.append(author)
    if authors:
        edition['authors'] = authors

def find_title(r, edition):
    # title
    f = r.get_field('245')
    if not f or 'a' not in f.contents:
        return
    title = ' '.join(x.strip(' /,;:') for x in f.contents['a'])
    edition['title'] = title
    if 'b' in f.contents:
        edition["subtitle"] = ' : '.join([x.strip(' /,;:') for x in f.contents['b']])
    if 'c' in f.contents:
        edition["by_statement"] = ' '.join(f.contents['c'])
    if 'h' in f.contents:
        edition["physical_format"] = ' '.join(f.contents['h'])

def find_other_titles(r, edition):
    other_titles = [' '.join(f.contents['a']) for f in r.get_fields('246') if 'a' in f.contents]

    for f in r.get_fields('730'):
        other_titles.append(' '.join([j for i,j in f.subfield_sequence if i.islower()]))

    for f in r.get_fields('740'):
        other_titles.append(' '.join(specific_subtags(f, 'apn')))

    if other_titles:
        edition["other_titles"] = other_titles

def find_work_title(r, edition):
    work_title = []
    f = r.get_field('240', default=None)
    if f:
        work_title.append(' '.join(specific_subtags(f, 'amnpr')))

    f = r.get_field('130', default=None)
    if f:
        work_title.append(' '.join([j for i,j in f.subfield_sequence if i.islower()]))

    if work_title:
        edition["work_titles"] = work_title

def find_edition(r, edition):
    e = []
    for f in r.get_fields('250'):
        e += [j for i,j in f.subfield_sequence]
    if e:
        edition['edition_name'] = ' '.join(e)

def find_publisher(r, edition):
    publisher = []
    publish_place = []
    for f in r.get_fields('260'):
        if 'b' in f.contents:
            publisher += [x.strip(" /,;:") for x in f.contents['b']]
        if 'a' in f.contents:
            publish_place += [x.strip(" /.,;:") for x in f.contents['a']]
    if publisher:
        edition["publishers"] = publisher
    if publish_place:
        edition["publish_places"] = publish_place

def find_pagination(r, edition):
    pagination = []
    for f in r.get_fields('300'):
        if 'a' in f.contents:
            pagination += f.contents['a']
    if pagination:
        edition["pagination"] = ' '.join(pagination)
        num = []
        for x in pagination:
            num += [ int(i) for i in re_int.findall(x.replace(',',''))]
            num += [ int(i) for i in re_int.findall(x) ]
        valid = [i for i in num if i < max_number_of_pages]
        if valid:
            edition["number_of_pages"] = max(valid)

def find_dewey_number(r, edition):
    # dewey_number
    fields = r.get_fields('082')
    if fields:
        dewey_number = []
        for f in fields:
            if 'a' in f.contents:
                dewey_number += f.contents['a']
        edition["dewey_decimal_class"] = dewey_number

def find_subjects(r, edition):
    fields = [
        ('600', 'abcd'),
        ('610', 'ab'),
        ('630', 'acdegnpqst'),
        ('650', 'a'),
        ('651', 'a'),
    ]

    subject = []
    subdivision_fields = 'vxyz'

    for tag, name_fields in fields:
        subject += [" -- ".join([" ".join(specific_subtags(f, name_fields))] + specific_subtags(f, subdivision_fields)) for f in r.get_fields(tag)]

    if subject:
        edition["subjects"] = subject

def remove_duplicates(seq):
    u = []
    for x in seq:
        if x not in u:
            u.append(x)
    return u

def find_subject_place(r, edition):
    subject_place = []
    for (tag, subtag) in [('651', 'a'), ('650', 'z')]:
        for f in r.get_fields(tag):
            if subtag in f.contents:
                subject_place += f.contents[subtag]

    if subject_place:
        edition["subject_places"] = remove_duplicates(subject_place)
        
def find_subject_time(r, edition):
    subject_time = []
    for (tag, subtag) in [('600', 'y'), ('650', 'y'), ('651', 'y')]:
        for f in r.get_fields(tag):
            if subtag in f.contents:
                subject_time += f.contents[subtag]

    if subject_time:
        edition["subject_times"] = remove_duplicates(subject_time)

def find_genre(r, edition):
    genres = []
    for (tag, subtag) in [('600', 'v'), ('650', 'v'), ('651', 'v')]:
        for f in r.get_fields(tag):
            if subtag in f.contents:
                genres += f.contents[subtag]

    if genres:
        edition["genres"] = remove_duplicates(genres)

def find_series(r, edition):
    series = []
    for tag in ('440', '490', '830'):
        for f in r.get_fields(tag):
            this_series = []
            for tag, value in f.subfield_sequence:
                if tag == 'a':
                    v = value.rstrip('.,; ')
                    if v:
                        this_series += [v]
                elif tag == 'v' and value:
                    this_series += [value]
            if this_series:
                series += [' -- '.join(this_series)]
    if series:
        edition["series"] = series

def find_description(r, edition):
    description = []
    for f in r.get_fields('520'):
        if 'a' not in f.contents:
            continue
        assert len(f.contents["a"]) == 1
        description.append(f.contents["a"][0])
    if description:
        edition["description"] = "\n\n".join(description)

def find_toc(r, edition): # table of contents
    toc = []
    for f in r.get_fields('505'):
        try:
            toc_line = []
            for subfield, value in f.subfield_sequence:
                if subfield == 'a':
                    toc.extend([x.strip() for x in value.split('--')])
                    continue
                if subfield == 't':
                    if toc_line:
                        toc.append(' -- '.join(toc_line))
                    toc_line = [value.strip(" /")]
                    continue
                toc_line.append(value.strip(" -"))
            if toc_line:
                toc.append(' -- '.join(toc_line))
        except AssertionError:
            print f.subfield_sequence
            raise
    if not toc:
        return
    toc2 = []
    for i in toc:
        if len(i) < 2048:
            toc2.append(i)
        else:
            sep_counts = [(i.count(sep), sep) for sep in '  ', ' - ']
            split_item = i.split(max(sep_counts)[1])
            # FIXME: omaggiodantealig00romauoft
            for j in split_item:
                if len(j) >= 2048:
                    raise BigToc
            toc2.extend(split_item)
    edition['table_of_contents'] = [{'title': i, 'type': '/type/toc_item'} for i in toc2]

def find_notes(r, edition):
    notes = []
    for tag in range(500,600):
        if tag in (505, 520):
            continue
        fields = r.get_fields(str(tag))
        for f in fields:
            x = [j for i,j in f.subfield_sequence if i.islower()]
            if x:
                notes.append(' '.join(x))
    if notes:
        edition["notes"] = notes

def find_lc_classification(r, edition):
    lc = []
    for f in r.get_fields('050'):
        if 'b' in f.contents:
            b = ' '.join(f.contents['b'])
            if 'a' in f.contents:
                lc += [' '.join([a, b]) for a in f.contents['a']]
            else:
                lc += [b]
        elif 'a' in f.contents:
            # zeitschriftfrd17beseuoft
            # 050  4 $d\Hammond\
            lc += f.contents['a']
    if lc:
        edition["lc_classifications"] = lc

def find_oclc(r, edition):
    oclc = []
    for f in r.get_fields('035'):
        if 'a' not in f.contents:
            continue
        for a in f.contents['a']:
            m = re_oclc.match(f.contents['a'][0])
            if m:
                v = m.group(1)
                if v not in oclc:
                    oclc.append(v)
    if oclc:
        edition['oclc_numbers'] = oclc

def find_isbn(r, edition):
    isbn_10 = []
    isbn_13 = []
    invalid = []
    odd_length = []
    for f in r.get_fields('020'):
        for subtag in 'a', 'z':
            if subtag in f.contents:
                for x in f.contents[subtag]:
                    m = re_isbn.match(x)
                    if m:
                        if subtag == 'z':
                            invalid.append(m.group(1))
                        elif len(m.group(1)) == 13:
                            isbn_13.append(m.group(1))
                        elif len(m.group(1)) == 10:
                            isbn_10.append(m.group(1))
                        else:
                            odd_length.append(m.group(1))

    if isbn_10:
        edition["isbn_10"] = isbn_10
    if isbn_13:
        edition["isbn_13"] = isbn_13
    if invalid:
        edition["isbn_invalid"] = invalid
    if odd_length:
        edition["isbn_odd_length"] = odd_length

def find_lccn(r, edition):
    for f in r.get_fields('010'):
        if not f or 'a' not in f.contents:
            continue
        for v in f.contents['a']:
            lccn = v.strip()
            if re_question.match(lccn):
                continue
            m = re_lccn.search(lccn)
            if m:
                edition["lccn"] = [m.group(1)]
                return

def find_url(r, edition):
    url = []
    for f in r.get_fields('856'):
        if 'u' not in f.contents:
            continue
        url += f.contents['u']
    if len(url):
        edition["url"] = url

def find_location(r, edition):
    loc = []
    for f in r.get_fields('852'):
        if 'a' not in f.contents:
            continue
        f_loc = f.contents['a']
        if not f_loc:
            continue
        loc += f_loc
    if loc:
        edition['location'] = loc

def encode_record_locator (r, file_locator):
    return ':'.join ([file_locator, str(r.record_pos()), str(r.record_len())])

def read_edition(r, edition):
    if len(r.get_fields('001')) > 1:
        return False

    find_title(r, edition)
    if not "title" in edition:
        return False
    find_other_titles(r, edition)
    find_work_title(r, edition)
    find_authors(r, edition)
    find_contributions(r, edition)
    find_edition(r, edition)
    find_publisher(r, edition)
    find_pagination(r, edition)
    find_subjects(r, edition)
    find_genre(r, edition)
    find_series(r, edition)
    find_description(r, edition)
    find_toc(r, edition)
    find_dewey_number(r, edition)
    find_lc_classification(r, edition)
    find_isbn(r, edition)
    find_oclc(r, edition)
    find_lccn(r, edition)
    find_url(r, edition)
    find_location(r, edition)

    if len(r.get_fields('008')) != 1:
        return False
    f = r.get_field('008')
    publish_date = str(f)[7:11]
    if publish_date != '||||':
        edition["publish_date"] = publish_date
    publish_country = str(f)[15:18]
    if publish_country not in ('|||', '   '):
        edition["publish_country"] = publish_country
    lang = str(f)[35:38]
    edition["languages"] = [{ 'key': '/l/' + lang }]
    return True

def parser(file_locator, input, bad_data):
    for r in MARC21BiblioFile (input):
        # only interested in books
        if r.marc_biblio_record_type() != 'a':
            continue
        if r.marc_biblio_bibliographic_level() != 'm':
            continue
        edition = {
            'source_record_loc': encode_record_locator (r, file_locator)
        }
        try:
            if read_edition(r, edition):
                yield edition
        except KeyboardInterrupt:
            raise
        except:
            raise
            bad_data(edition['source_record_loc'])

if __name__ == '__main__':
    for x in parser(sys.argv[1], sys.argv[2], sys.stdin):
        print x

