# fast parse for merge
# TODO: title and author
# TODO: handle MARC8 charset

import re

re_question = re.compile('^\?+$')
re_lccn = re.compile('(...\d+).*')
re_int = re.compile ('\d{2,}')
re_isbn = re.compile('([^ ()]+[\dX])(?: \((?:v\. (\d+)(?: : )?)?(.*)\))?')
re_oclc = re.compile ('^\(OCoLC\).*?0*(\d+)')

# no monograph should be longer than 50,000 pages
max_number_of_pages = 50000

def get_subfields(line, want):
    want = set(want)
    assert line[2] == '\x1f'
    for i in line[3:-1].split('\x1f'):
        if i[0] in want:
            yield i[0], i[1:]

def get_tag_lines(data, want):
    want = set(want)
    dir_end = data.find(chr(30))
    directory = data[24:dir_end]
    assert len(directory) % 12 == 0

    fields = []

    for i in range(len(directory) / 12):
        line = directory[i*12:(i+1)*12]
        tag = line[:3]
        if tag not in want:
            continue
        length = int(line[3:7])
        offset = int(line[7:12])
        tag_line = data[dir_end+offset + 1:dir_end+1+length+offset]
        assert ord(tag_line[-1]) == 30
        fields.append((tag, tag_line))
    return fields

def read_edition(data):
    edition = {}
    want = ['008', '010', '020', '035', '100', '110', '111', '245', '260', '300']
    fields = get_tag_lines(data, want)
    for tag, line in fields:
        if tag == '008':
            edition['publish_date'] = line[7:11]
            edition['publish_country'] = line[15:18]
            edition['languages'] = line[35:38]
        if tag == '010':
            for k, v in get_subfields(line, ['a']):
                lccn = v.strip()
                if re_question.match(lccn):
                    continue
                m = re_lccn.search(lccn)
                if m:
                    edition.setdefault('lccn', []).append(m.group(1))
        if tag == '020':
            for k, v in get_subfields(line, ['a']):
                m = re_isbn.match(v)
                if m:
                    edition.setdefault('isbn', []).append(m.group(1))
        if tag == '035':
            for k, v in get_subfields(line, ['a']):
                m = re_oclc.match(v)
                if m:
                    edition.setdefault('oclc', []).append(m.group(1))
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
