from catalog.marc.MARC21Biblio import *

import sys, re

record_id_delimiter = ":"
record_loc_delimiter = ":"

re_isbn = re.compile('([^ ()]+[\dX])(?: \((?:v\. (\d+)(?: : )?)?(.*)\))?')
re_lccn = re.compile('(...\d+).*')
re_date = map (re.compile, ['(?P<birth_date>\d+\??)-(?P<death>\d+\??)',
                            '(?P<birth_date>\d+\??)-',
                            'b\.? (?P<birth_date>(?:ca\. )?\d+\??)',
                            'd\.? (?P<death>(?:ca\. )?\d+\??)',
                            '(?P<birth_date>.*\d+.*)-(?P<death>.*\d+.*)',
                            '^(?P<birth_date>[^-]*\d+[^-]+ cent\.[^-]*)$'])

def specific_subtags(f, subtags):
    return [j for i, j in f.subfield_sequence if i in subtags]

def parse_date(date):
    for r in re_date:
        m = r.search(date)
        if m:
            return m.groupdict()
    return {}

def find_authors (r, edition):
    authors = []
    for tag, subtags in [ ('100', 'abc'), ('110', 'ab'), ('111', 'acdn') ]:
        for f in r.get_fields(tag):
            author = {}
            if tag == '100' and 'd' in f.contents:
                author = parse_date(f.contents['d'][0])
            author['name'] = " ".join([j.strip(' /,;:') for i, j in f.subfield_sequence if i in subtags])
            if tag == '100':
                db_name = [j.strip(' /,;:') for i, j in f.subfield_sequence if i in 'abcd']
                author['db_name'] = " ".join(db_name)
            else:
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

def find_title(r, edition):
    # title
    f = r.get_field('245')
    edition["title"] = ' '.join(x.strip(' /,;:') for x in f.contents['a'])
    if 'b' in f.contents:
        edition["subtitle"] = [x.strip(' /,;:') for x in f.contents['b']]
    if 'c' in f.contents:
        edition["by_statement"] = f.contents['c']
    if 'h' in f.contents:
        edition["physical_format"] = f.contents['h']

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
    f = r.get_field('240')
    if f:
        work_title.append(' '.join(specific_subtags(f, 'amnpr')))

    f = r.get_field('130')
    if f:
        work_title.append(' '.join([j for i,j in f.subfield_sequence if i.islower()]))

    if work_title:
        edition["work_title"] = work_title

def find_edition(r, edition):
    e = []
    for f in r.get_fields('250'):
        e += [j for i,j in f.subfield_sequence]
    if edition:
        edition["edition"] = ' '.join(e)

def find_publisher(r, edition):
    publisher = []
    publish_place = []
    for f in r.get_fields('260'):
        if 'b' in f.contents:
            publisher += [x.strip(" /,;:") for x in f.contents['b']]
        if 'a' in f.contents:
            publish_place += [x.strip(" /.,;:") for x in f.contents['a']]
    if publisher:
        edition["publisher"] = publisher
    if publish_place:
        edition["publish_place"] = publish_place

def find_pagination(r, edition):
    pagination = []
    for f in r.get_fields('300'):
        pagination += f.contents['a']
    if pagination:
        edition["pagination"] = pagination
        num = []
        for x in pagination:
            num += re_int.findall(x)
        if num:
            edition["number_of_pages"] = max([int(x) for x in num])

def find_dewey_number(r, edition):
    # dewey_number
    fields = r.get_fields('082')
    if fields:
        dewey_number = []
        for f in fields:
            if 'a' in f.contents:
                dewey_number += f.contents['a']
        edition["dewey_number"] = dewey_number

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
        subject += [" ".join(specific_subtags(f, name_fields) + ["--".join(specific_subtags(f, subdivision_fields))]) for f in r.get_fields(tag)]

    if subject:
        edition["subject"] = subject

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
        edition["subject_place"] = remove_duplicates(subject_place)
        
def find_subject_time(r, edition):
    subject_time = []
    for (tag, subtag) in [('600', 'y'), ('650', 'y'), ('651', 'y')]:
        for f in r.get_fields(tag):
            if subtag in f.contents:
                subject_time += f.contents[subtag]

    if subject_time:
        edition["subject_time"] = remove_duplicates(subject_time)

def find_genre(r, edition):
    genre = []
    for (tag, subtag) in [('600', 'v'), ('650', 'v'), ('651', 'v')]:
        for f in r.get_fields(tag):
            if subtag in f.contents:
                genre += f.contents[subtag]

    if genre:
        edition["genre"] = remove_duplicates(genre)

def find_series(r, edition):
    series = []
    for tag in ('440', '490', '830'):
        for f in r.get_fields(tag):
            series += specific_subtags(f, 'av')
    if series:
        edition["series"] = series

def find_description(r, edition):
    description = []
    for f in r.get_fields('520'):
        assert len(f.contents["a"]) == 1
        description.append(f.contents["a"][0])
    if description:
        edition["description"] = "\n\n".join(description)

def find_table_of_contents(r, edition):
    toc = [' '.join(specific_subtags(f, 'art')) for f in r.get_fields('505')]
    if toc:
        edition["table_of_contents"] = toc

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
            lc += [' '.join([a, b]) for a in f.contents['a']]
        else:
            lc += f.contents['a']
    if lc:
        edition["LC_classification"] = lc

def find_isbn(r, edition):
    isbn = []
    for f in r.get_fields('020'):
        for subtag in 'a', 'z':
            if subtag in f.contents:
                for x in f.contents[subtag]:
                    m = re_isbn.match(x)
                    if m:
                        isbn.append(m.group(1))

    if isbn:
        edition["ISBN"] = isbn

def find_lccn(r, edition):
    if 'a' not in r.get_field('010').contents:
        return
    lccn = r.get_field('010').contents['a'][0].strip()
    m = re_lccn.match(lccn)
    assert m
    edition["lccn"] = m.group(1)

def encode_record_locator (r, file_locator):
    return record_loc_delimiter.join ([file_locator, str(r.record_pos()), str(r.record_len())])

def parser(source_id, file_locator, input):
    for r in MARC21BiblioFile (input):
        edition = {}
        edition['source_record_loc'] = [encode_record_locator (r, file_locator)]
        curr_loc = edition['source_record_loc'][0]
        field_1 = r.get_field_value('001')
        field_3 = r.get_field_value('003')
        if field_1 and field_3:
            edition['source_record_id'] = [record_id_delimiter.join ([source_id,
                field_1.strip(), field_3.strip()])]

        find_table_of_contents(r, edition)
        find_authors(r, edition)
        find_contributions(r, edition)
        find_title(r, edition)
        find_other_titles(r, edition)
        find_work_title(r, edition)
        find_edition(r, edition)
        find_publisher(r, edition)
        find_subjects(r, edition)
        find_subject_place(r, edition)
        find_subject_time(r, edition)
        find_genre(r, edition)
        find_series(r, edition)
        find_description(r, edition)
        find_table_of_contents(r, edition)
        find_dewey_number(r, edition)
        find_lc_classification(r, edition)
        find_isbn(r, edition)
        find_lccn(r, edition)
        find_subjects(r, edition)

        f = r.get_field('008')
        edition["publish_date"] = str(f)[7:11]
        edition["language"] = "ISO:" + str(f)[35:38]

        yield edition

if __name__ == '__main__':
    for x in parser(sys.argv[1], sys.argv[2], sys.stdin):
        print x
