# fast parse for merge

import re
from pymarc import MARC8ToUnicode
import mnemonics
from unicodedata import normalize
from openlibrary.catalog.utils import tidy_isbn

re_real_book = re.compile('(pbk|hardcover|alk[^a-z]paper|cloth)', re.I)

def translate(bytes_in, leader_says_marc8=False):
    marc8 = MARC8ToUnicode(quiet=True)
    try:
        if leader_says_marc8:
            data = marc8.translate(mnemonics.read(bytes_in))
        else:
            data = bytes_in.decode('utf-8')
        return normalize('NFC', data)
    except:
        print 'translate error for:', `bytes_in`
        print 'marc8:', leader_says_marc8
        raise

re_question = re.compile('^\?+$')
re_lccn = re.compile('(...\d+).*')
re_letters_and_bad = re.compile('[A-Za-z\x80-\xff]')
re_int = re.compile ('\d{2,}')
re_isbn = re.compile('([^ ()]+[\dX])(?: \((?:v\. (\d+)(?: : )?)?(.*)\))?')
re_oclc = re.compile ('^\(OCoLC\).*?0*(\d+)')

re_normalize = re.compile('[^\w ]')
re_whitespace = re.compile('\s+')

def normalize_str(s):
    s = re_normalize.sub('', s.strip())
    s = re_whitespace.sub(' ', s)
    return str(s.lower())

# no monograph should be longer than 50,000 pages
max_number_of_pages = 50000

class InvalidMarcFile(Exception):
    pass

def read_file(f):
    buf = None
    while 1:
        if buf:
            length = buf[:5]
            try:
                int_length = int(length)
            except:
                print `buf`
                raise
        else:
            length = f.read(5)
            buf = length
        if length == "":
            break
        if not length.isdigit():
            print 'not a digit:', `length`
            raise InvalidMarcFile
        int_length = int(length)
        data = buf + f.read(int_length - len(buf))
        buf = None
        if not data.endswith("\x1e\x1d"):
            # skip bad record, should warn somehow
            end_index = data.rfind('\x1e\x1d')
            if end_index != -1:
                end = end_index + 2
                yield (data[:end], end)
                buf = data[end:]
                continue
        if data.find('\x1d') == -1:
            data += f.read(40)
            int_length = data.find('\x1d') + 1
            assert int_length
            buf = data[int_length:]
            data = data[:int_length]
        assert data.endswith("\x1e\x1d")
        if len(data) < int_length:
            break
        yield (data, int_length)

def read_author_person(line, is_marc8):
    name = []
    name_and_date = []
    for k, v in get_subfields(line, ['a', 'b', 'c', 'd'], is_marc8):
        if k != 'd':
            v = v.strip(' /,;:')
            name.append(v)
        name_and_date.append(v)
    if not name:
        return []

    return [{ 'db_name': u' '.join(name_and_date), 'name': u' '.join(name), }]

# exceptions:
class SoundRecording(Exception):
    pass

class NotBook(Exception):
    pass

class BadDictionary(Exception):
    pass

def read_full_title(line, accept_sound = False, is_marc8=False):
        if not accept_sound and v.lower().startswith("[sound"):
            raise SoundRecording
        if v.lower().startswith("[graphic") or v.lower().startswith("[cartographic"):
            raise NotBook
    title = [v.strip(' /,;:') for k, v in get_subfields(line, ['a', 'b'], is_marc8)]
    return ' '.join([t for t in title if t])

def read_short_title(line, is_marc8):
    title = normalize_str(read_full_title(line, is_marc8))[:25].rstrip()
    if title:
        return [title]
    else:
        return []

def read_title_and_subtitle(data, is_marc8): # not currently used
    line = get_first_tag(data, set(['245']))
    contents = get_contents(line, ['a', 'b', 'c', 'h'], is_marc8)

    title = None
    if 'a' in contents:
        title = ' '.join(x.strip(' /,;:') for x in contents['a'])
    elif 'b' in contents:
        title = contents['b'][0].strip(' /,;:')
        del contents['b'][0]
    subtitle = None
    if 'b' in contents and contents['b']:
        subtitle = ' : '.join([x.strip(' /,;:') for x in contents['b']])
    return (title, subtitle)

def get_raw_subfields(line, want):
    # no translate
    want = set(want)
    #assert line[2] == '\x1f'
    for i in line[3:-1].split('\x1f'):
        if i and i[0] in want:
            yield i[0], i[1:]

def get_all_subfields(line, is_marc8=False):
    for i in line[3:-1].split('\x1f'):
        if i:
            j = translate(i, is_marc8)
            yield j[0], j[1:]

def get_subfields(line, want, is_marc8=False):
    want = set(want)
    #assert line[2] == '\x1f'
    for i in line[3:-1].split('\x1f'):
        if i and i[0] in want:
            yield i[0], translate(i[1:], is_marc8)

def read_directory(data):
    dir_end = data.find('\x1e')
    if dir_end == -1:
        raise BadDictionary
    directory = data[24:dir_end]
    if len(directory) % 12 != 0:
        print 'directory is the wrong size'
        # directory is the wrong size
        # sometimes the leader includes some utf-8 by mistake
        directory = data[:dir_end].decode('utf-8')[24:]
        if len(directory) % 12 != 0:
            print len(directory) / 12
            raise BadDictionary
    iter_dir = (directory[i*12:(i+1)*12] for i in range(len(directory) / 12))
    return dir_end, iter_dir

def get_tag_line(data, line):
    length = int(line[3:7])
    offset = int(line[7:12])

    # handle off-by-one errors in MARC records
    try:
        if data[offset] != '\x1e':
            offset += data[offset:].find('\x1e')
        last = offset+length
        if data[last] != '\x1e':
            length += data[last:].find('\x1e')
    except IndexError:
        pass

    tag_line = data[offset + 1:offset + length + 1]
    if not line[0:2] == '00':
        # marc_western_washington_univ/wwu_bibs.mrc_revrev.mrc:636441290:1277
        if tag_line[1:8] == '{llig}\x1f':
            tag_line = tag_line[0] + u'\uFE20' + tag_line[7:]
    return tag_line

re_dates = re.compile('^\(?(\d+-\d*|\d*-\d+)\)?$')

def get_person_content(line, is_marc8):
    contents = {}
    for k, v in get_subfields(line, ['a', 'b', 'c', 'd', 'q'], is_marc8):
        if k != 'd' and re_dates.match(v): # wrong subtag
            k = 'd'
        contents.setdefault(k, []).append(v)
    return contents

def get_contents(line, want):
    contents = {}
    for k, v in get_subfields(line, want, is_marc8):
        contents.setdefault(k, []).append(v)
    return contents

def get_lower_subfields(line, is_marc8):
    if len(line) < 4: 
        return [] # http://openlibrary.org/show-marc/marc_university_of_toronto/uoft.marc:2479215:693
    return [translate(i[1:], is_marc8) for i in line[3:-1].split('\x1f') if i and i[0].islower()]

def get_subfield_values(line, want, is_marc8):
    return [v for k, v in get_subfields(line, want, is_marc8)]

def get_all_tag_lines(data):
    dir_end, iter_dir = read_directory(data)
    data = data[dir_end:]
    for line in iter_dir:
        yield (line[:3], get_tag_line(data, line))
    #return [(line[:3], get_tag_line(data, line)) for line in iter_dir]

def get_first_tag(data, want): # return first line of wanted tag
    dir_end, iter_dir = read_directory(data)
    data = data[dir_end:]
    for line in iter_dir:
        if line[:3] in want:
            return get_tag_line(data, line)

def get_tag_lines(data, want):
    want = set(want)
    dir_end, iter_dir = read_directory(data)
    data = data[dir_end:]
    return [(line[:3], get_tag_line(data, line)) for line in iter_dir if line[:3] in want]

def read_control_number(line, is_marc8):
    assert line[-1] == '\x1e'
    return [line[:-1]]

def read_lccn(line, is_marc8):
    found = []
    for k, v in get_raw_subfields(line, ['a']):
        lccn = v.strip()
        if re_question.match(lccn):
            continue
        m = re_lccn.search(lccn)
        if not m:
            continue
        # remove letters and bad chars
        lccn = re_letters_and_bad.sub('', m.group(1)).strip()
        if lccn:
            found.append(lccn)
    return found

def read_isbn(line, is_marc8):
    found = []
    if line.find('\x1f') != -1:
        for k, v in get_raw_subfields(line, ['a', 'z']):
            m = re_isbn.match(v)
            if m:
                found.append(m.group(1))
    else:
        m = re_isbn.match(line[3:-1])
        if m:
            found = [m.group(1)]
    return map(str, tidy_isbn(found))

def read_oclc(line, is_marc8):
    found = []
    for k, v in get_raw_subfields(line, ['a']):
        m = re_oclc.match(v)
        if m:
            found.append(m.group(1))
    return found

def read_publisher(line, is_marc8):
    return [i for i in (v.strip(' /,;:') for k, v in get_subfields(line, ['b'], is_marc8)) if i]

def read_author_org(line, is_marc8):
    name = " ".join(v.strip(' /,;:') for k, v in get_subfields(line, ['a', 'b'], is_marc8))
    return [{ 'name': name, 'db_name': name, }]

def read_author_event(line, is_marc8):
    name = " ".join(v.strip(' /,;:') for k, v in get_subfields(line, ['a', 'b', 'd', 'n'], is_marc8))
    return [{ 'name': name, 'db_name': name, }]

def add_oclc(edition):
    if 'control_numer' not in edition:
        return
    oclc = edition['control_number'][0]
    assert oclc.isdigit()
    edition.setdefault('oclc', []).append(oclc)

def index_fields(data, want, check_author = True):
    if str(data)[6:8] != 'am': # only want books
        return None
    is_marc8 = data[9] != 'a'
    edition = {}
    # ['006', '010', '020', '035', '245']
    author = {
        '100': 'person',
        '110': 'org',
        '111': 'even',
    }


    if check_author:
        want += author.keys()
    fields = get_tag_lines(data, ['006', '008', '260'] + want)
    read_tag = {
        '001': (read_control_number, 'control_number'),
        '010': (read_lccn, 'lccn'),
        '020': (read_isbn, 'isbn'),
        '035': (read_oclc, 'oclc'),
        '245': (read_short_title, 'title'),
    }

    seen_008 = False
    oclc_001 = False
    is_real_book = False

    tag_006_says_electric = False
    for tag, line in fields:
        if tag == '003': # control number identifier
            if line.lower().startswith('ocolc'):
                oclc_001 = True
            continue
        if tag == '006':
            if line[0] == 'm': # don't want electronic resources
                tag_006_says_electric = True
            continue
        if tag == '008':
            if seen_008: # dup
                return None
            seen_008 = True
            continue
        if tag == '020' and re_real_book.search(line):
            is_real_book = True
        if tag == '260': 
            if line.find('\x1fh[sound') != -1: # sound recording
                return None
            continue

        if tag in author:
            if 'author' in edition:
                return None
            else:
                edition['author'] = author[tag]
            continue
        assert tag in read_tag
        proc, key = read_tag[tag]
        try:
            found = proc(line, is_marc8)
        except SoundRecording:
            return None
        if found:
            edition.setdefault(key, []).extend(found)
    if oclc_001:
        add_oclc(edition)
    if 'control_number' in edition:
        del edition['control_number']
    if not seen_008:
        return None
#    if 'title' not in edition:
#        return None
    if tag_006_says_electric and not is_real_book:
        return None
    return edition

def read_edition(data, accept_electronic = False):
    is_marc8 = data[9] != 'a'
    edition = {}
    want = ['001', '003', '006', '008', '010', '020', '035', \
            '100', '110', '111', '700', '710', '711', '245', '260', '300']
    fields = get_tag_lines(data, want)
    read_tag = [
        ('001', read_control_number, 'control_number'),
        ('010', read_lccn, 'lccn'),
        ('020', read_isbn, 'isbn'),
        ('035', read_oclc, 'oclc'),
        ('100', read_author_person, 'authors'),
        ('110', read_author_org, 'authors'),
        ('111', read_author_event, 'authors'),
        ('700', read_author_person, 'contribs'),
        ('710', read_author_org, 'contribs'),
        ('711', read_author_event, 'contribs'),
        ('260', read_publisher, 'publishers'),
    ]

    oclc_001 = False
    tag_006_says_electric = False
    is_real_book = False
    for tag, line in fields:
        if tag == '003': # control number identifier
            if line.lower().startswith('ocolc'):
                oclc_001 = True
            continue
        if tag == '006':
            if line[0] == 'm':
                tag_006_says_electric = True
            continue
        if tag == '008': # not interested in '19uu' for merge
            #assert len(line) == 41 usually
            if line[7:11].isdigit(): 
                edition['publish_date'] = line[7:11]
            edition['publish_country'] = line[15:18]
            continue
        if tag == '020' and re_real_book.search(line):
            is_real_book = True
        for t, proc, key in read_tag:
            if t != tag:
                continue
            found = proc(line, is_marc8=is_marc8)
            if found:
                edition.setdefault(key, []).extend(found)
            break
        if tag == '245':
            edition['full_title'] = read_full_title(line, is_marc8=is_marc8)
            continue
        if tag == '300':
            for k, v in get_subfields(line, ['a'], is_marc8):
                num = [ int(i) for i in re_int.findall(v) ]
                num = [i for i in num if i < max_number_of_pages]
                if not num:
                    continue
                max_page_num = max(num)
                if 'number_of_pages' not in edition \
                        or max_page_num > edition['number_of_pages']:
                    edition['number_of_pages'] = max_page_num
    if oclc_001:
        add_oclc(edition)
    if 'control_number' in edition:
        del edition['control_number']
    if not accept_electronic and tag_006_says_electric and not is_real_book:
        print 'electronic resources'
        return None

    return edition

def handle_wrapped_lines(iter):
    cur_lines = []
    cur_tag = None
    maybe_wrap = False
    for t, l in iter:
        if len(l) > 500 and l.endswith('++\x1e'):
            assert not cur_tag or cur_tag == t
            cur_tag = t
            cur_lines.append(l)
            continue
        if cur_lines:
            yield cur_tag, cur_lines[0][:-3] + ''.join(i[2:-3] for i in cur_lines[1:]) + l[2:]
            cur_tag = None
            cur_lines = []
            continue
        yield t, l
    assert not cur_lines

def split_line(s):
    # TODO: document this function
    pos = -1
    marks = []
    while 1:
        pos = s.find('\x1f', pos + 1)
        if pos == -1:
            break
        if s[pos+1] != '\x1b':
            marks.append(pos)
    if not marks:
        return [('v', s)]

    ret = []
    if s[:marks[0]]:
        ret.append(('v', s[:marks[0]]))
    for i in range(len(marks)):
        m = marks[i]
        ret.append(('k', s[m+1:m+2]))
        if len(marks) == i+1:
            if s[m+2:]:
                ret.append(('v', s[m+2:]))
        else:
            if s[m+2:marks[i+1]]:
                ret.append(('v', s[m+2:marks[i+1]]))
    return ret

def test_wrapped_lines():
    data = open('test_data/wrapped_lines').read()
    ret = list(handle_wrapped_lines(get_tag_lines(data, ['520'])))
    assert len(ret) == 2
    a, b = ret
    assert a[0] == '520' and b[0] == '520'
    assert len(a[1]) == 2295
    assert len(b[1]) == 248

def test_translate():
    assert translate('Vieira, Claudio Bara\xe2una,') == u'Vieira, Claudio Bara\xfana,'

def test_read_oclc():
    from pprint import pprint
    for f in ('oregon_27194315',):
        data = open('test_data/' + f).read()
        i = index_fields(data, ['001', '003', '010', '020', '035', '245'])
        assert 'oclc' in i
        e = read_edition(data)
        assert 'oclc' in e

def test_record():
    assert read_edition(open('test_data/lc_0444897283').read())

def test_empty():
    assert read_edition('') == {}

def bad_marc_line():
    line = '0 \x1f\xe2aEtude objective des ph\xe2enom\xe1enes neuro-psychiques;\x1e'
    assert list(get_all_subfields(line)) == [(u'\xe1', u'Etude objective des ph\xe9nom\xe8nes neuro-psychiques;')]

def test_index_fields():
    data = open('test_data/ithaca_college_75002321').read()
    lccn = index_fields(data, ['010'])['lccn'][0]
    assert lccn == '75002321'

def test_ia_charset():
    data = open('test_data/histoirereligieu05cr_meta.mrc').read()
    line = list(get_tag_lines(data, set(['100'])))[0][1]
    a = list(get_all_subfields(line, ia_bad_charset=True))[0][1]
    expect = u'Cr\xe9tineau-Joly, J.'
    assert a == expect
