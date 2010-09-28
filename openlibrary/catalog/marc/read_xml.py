import xml.etree.ElementTree as et
import xml.parsers.expat
from pprint import pprint
import re, sys, codecs
from time import sleep
from unicodedata import normalize

re_question = re.compile('^\?+$')
re_lccn = re.compile('(...\d+).*')
re_letters = re.compile('[A-Za-z]')
re_int = re.compile ('\d{2,}')
re_isbn = re.compile('([^ ()]+[\dX])(?: \((?:v\. (\d+)(?: : )?)?(.*)\))?')
re_oclc = re.compile ('^\(OCoLC\).*?0*(\d+)')

# no monograph should be longer than 50,000 pages
max_number_of_pages = 50000

slim = '{http://www.loc.gov/MARC21/slim}'
leader_tag = slim + 'leader'
data_tag = slim + 'datafield'
control_tag = slim + 'controlfield'
subfield_tag = slim + 'subfield'
collection_tag = slim + 'collection'
record_tag = slim + 'record'

class BadXML:
    pass

def read_author_person(line):
    name = []
    name_and_date = []
    for k, v in get_subfields(line, ['a', 'b', 'c', 'd']):
        if k != 'd':
            v = v.strip(' /,;:')
            name.append(v)
        name_and_date.append(v)
    if not name:
        return []

    return [{ 'db_name': ' '.join(name_and_date), 'name': ' '.join(name), }]

def read_full_title(line):
    title = [v.strip(' /,;:') for k, v in get_subfields(line, ['a', 'b'])]
    return ' '.join([t for t in title if t])

def read_lccn(line):
    found = []
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
    return found

def read_isbn(line):
    found = []
    for k, v in get_subfields(line, ['a', 'z']):
        m = re_isbn.match(v)
        if m:
            found.append(m.group(1))
    return [i.replace('-', '') for i in found]

def read_oclc(line):
    found = []
    for k, v in get_subfields(line, ['a']):
        m = re_oclc.match(v)
        if m:
            found.append(m.group(1))
    return found

def read_publisher(line):
    return [v.strip(' /,;:') for k, v in get_subfields(line, ['b'])]

def read_author_org(line):
    name = " ".join(v.strip(' /,;:') for k, v in get_subfields(line, ['a', 'b']))
    return [{ 'name': name, 'db_name': name, }]

def read_author_event(line):
    name = " ".join(v.strip(' /,;:') for k, v in get_subfields(line, ['a', 'b', 'd', 'n']))
    return [{ 'name': name, 'db_name': name, }]

def get_tag_lines(f, want):
    tree = et.parse(f)
    root = tree.getroot()
    if root.tag == collection_tag:
        root = root[0]
    assert root.tag == record_tag
    fields = []
    for i in root:
        if i.tag == leader_tag and i.text[6:8] != 'am': # only want books:
            return []
        if i.tag != data_tag and i.tag != control_tag:
            continue
        tag = i.attrib['tag']
        if tag == '':
            raise BadXML
        if tag not in want:
            continue
        if i.tag == control_tag:
            fields.append((tag, i.text))
            continue
        field = {
            'ind1': i.attrib['ind1'],
            'ind2': i.attrib['ind2'],
            'seq': [],
        }
        for k in i:
            assert k.tag == subfield_tag
            if k.attrib['code'] == '':
                raise BadXML
            field['seq'].append((k.attrib['code'], k.text if k.text else ''))
        fields.append((tag, field))
    return fields

def get_subfields(line, want):
    want = set(want)
    return (i for i in line['seq'] if i[0] in want)

def read_edition(f):
    edition = {}
    want = ['008', '010', '020', '035', \
            '100', '110', '111', '700', '710', '711', '245', '260', '300']
    fields = get_tag_lines(f, want)
    read_tag = [
        ('010', read_lccn, 'lccn'),
        ('020', read_isbn, 'isbn'),
        ('035', read_oclc, 'oclc'),
        ('100', read_author_person, 'authors'),
        ('110', read_author_org, 'authors'),
        ('111', read_author_event, 'authors'),
        ('700', read_author_person, 'contribs'),
        ('710', read_author_org, 'contribs'),
        ('711', read_author_event, 'contribs'),
        ('260', read_publisher, 'publisher'),
    ]

    for tag, line in fields:
        # http://openlibrary.org/b/OL7074573M
        # if tag == '006':
        #    if line[0] == 'm':
        #        return None
        #    continue
        if tag == '008':
            publish_date = unicode(line)[7:11]
            if publish_date.isdigit():
                edition["publish_date"] = publish_date
            publish_country = unicode(line)[15:18]
            if publish_country not in ('|||', '   '):
                edition["publish_country"] = publish_country
            continue
        for t, proc, key in read_tag:
            if t != tag:
                continue
            found = proc(line)
            if found:
                edition.setdefault(key, []).extend(found)
            break
        if tag == '245':
            edition['full_title'] = read_full_title(line)
            continue
        if tag == '300':
            for k, v in get_subfields(line, ['a']):
                num = [ int(i) for i in re_int.findall(v) ]
                num = [i for i in num if i < max_number_of_pages]
                if not num:
                    continue
                max_page_num = max(num)
                if 'number_of_pages' not in edition \
                        or max_page_num > edition['number_of_pages']:
                    edition['number_of_pages'] = max_page_num
    return edition

def test_parse():
    expect = {
        'publisher': ['Univ. Press'],
        'number_of_pages': 128,
        'full_title': 'Human efficiency and levels of intelligence.', 
        'publish_date': '1920',
        'publish_country': 'nju',
        'authors': [{
            'db_name': 'Goddard, Henry Herbert.',
            'name': 'Goddard, Henry Herbert.'
        }],
    }

    assert read_edition("humanefficiencyl00godduoft") == expect

def test_xml():
    f = open('test_data/nybc200247_marc.xml')
    lines = get_tag_lines(f, ['245'])
    for tag, line in lines:
        title = list(get_subfields(line, ['a']))[0][1]
        print title
        print normalize('NFC', title)
#    print read_edition(open('test_data/nybc200247_marc.xml'))['full_title']

def test_yale_xml():
    f = open('test_data/39002054008678.yale.edu_marc.xml')
    read_edition(f)
    f.close()

#test_yale_xml()
