"""Deprecated module,
MARC parsing should be done by catalog.marc.parse instead.
"""

import re
from deprecated import deprecated
from pymarc import MARC8ToUnicode
from unicodedata import normalize

from openlibrary.catalog.marc import mnemonics
from openlibrary.catalog.utils import tidy_isbn


re_real_book = re.compile('(pbk|hardcover|alk[^a-z]paper|cloth)', re.I)


@deprecated('Use openlibrary.catalog.marc.MarcBinary instead.')
def translate(bytes_in, leader_says_marc8=False):
    """
    Converts a binary MARC field value to unicode str,
    from either MARC8 or UTF8 encoded bytes.

    :param bytes_in bytes:
    :rtype: str
    """
    assert isinstance(bytes_in, bytes)
    marc8 = MARC8ToUnicode(quiet=True)
    if leader_says_marc8:
        data = marc8.translate(mnemonics.read(bytes_in))
    else:
        data = bytes_in.decode('utf-8')
    return normalize('NFC', data)


re_question = re.compile(r'^\?+$')
re_letters_and_bad = re.compile('[A-Za-z\x80-\xff]')
re_int = re.compile(r'\d{2,}')
re_isbn = re.compile(r'([^ ()]+[\dX])(?: \((?:v\. (\d+)(?: : )?)?(.*)\))?')


re_normalize = re.compile(r'[^\w ]')
re_whitespace = re.compile(r'\s+')


@deprecated
def normalize_str(s):
    s = re_normalize.sub('', s.strip())
    s = re_whitespace.sub(' ', s)
    return str(s.lower())


# no monograph should be longer than 50,000 pages
max_number_of_pages = 50000


class InvalidMarcFile(Exception):
    pass


@deprecated('Use catalog.marc.parse instead.')
def read_file(f):
    """
    Generator which seeks? for start of a MARC record and
    returns the proper data and its length.

    :param str f: Raw binary MARC data
    :rtype: (str, int)
    :return: Data, length
    """
    buf = None
    while True:
        if buf:
            length = buf[:5]
            int_length = int(length)
        else:
            length = f.read(5)
            buf = length
        if length == "":
            break
        if not length.isdigit():
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


@deprecated
def read_author_person(line, is_marc8=False):
    name = []
    name_and_date = []
    for k, v in get_subfields(line, ['a', 'b', 'c', 'd'], is_marc8):
        if k != 'd':
            v = v.strip(' /,;:')
            name.append(v)
        name_and_date.append(v)
    if not name:
        return []

    return [
        {
            'db_name': ' '.join(name_and_date),
            'name': ' '.join(name),
        }
    ]


# exceptions:
class SoundRecording(Exception):
    pass


class NotBook(Exception):
    pass


class BadDictionary(Exception):
    pass


@deprecated
def read_title_and_subtitle(data, is_marc8=False):
    line = get_first_tag(data, {'245'})
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


@deprecated
def get_raw_subfields(line, want):
    # no translate
    want = set(want)
    # assert line[2] == '\x1f'
    for i in line[3:-1].split('\x1f'):
        if i and i[0] in want:
            yield i[0], i[1:]


@deprecated('Use catalog.marc.MarcBinary instead.')
def get_all_subfields(line, is_marc8=False):
    for i in line[3:-1].split('\x1f'):
        if i:
            j = translate(i, is_marc8)
            yield j[0], j[1:]


@deprecated
def get_subfields(line, want, is_marc8=False):
    want = set(want)
    # assert line[2] == '\x1f'
    for i in line[3:-1].split('\x1f'):
        if i and i[0] in want:
            yield i[0], translate(i[1:], is_marc8)


@deprecated('Use catalog.marc.MarcBinary instead.')
def read_directory(data):
    dir_end = data.find(b'\x1e')
    if dir_end == -1:
        raise BadDictionary
    directory = data[24:dir_end]
    if len(directory) % 12 != 0:
        # directory is the wrong size
        # sometimes the leader includes some utf-8 by mistake
        directory = data[:dir_end].decode('utf-8')[24:]
        if len(directory) % 12 != 0:
            raise BadDictionary
    iter_dir = (directory[i * 12 : (i + 1) * 12] for i in range(len(directory) // 12))
    return dir_end, iter_dir


@deprecated('Use catalog.marc.MarcBinary instead.')
def get_tag_line(data, line):
    # Still used by catalog/marc/html.py
    length = int(line[3:7])
    offset = int(line[7:12])

    # handle off-by-one errors in MARC records
    if data[offset] != b'\x1e':
        offset += data[offset:].find(b'\x1e')
    last = offset + length
    if data[last] != b'\x1e':
        length += data[last:].find(b'\x1e')
    tag_line = data[offset + 1 : offset + length + 1]
    return tag_line


@deprecated
def get_tag_lines(data, want):
    want = set(want)
    dir_end, iter_dir = read_directory(data)
    data = data[dir_end:]
    return [
        (line[:3], get_tag_line(data, line)) for line in iter_dir if line[:3] in want
    ]


@deprecated
def get_all_tag_lines(data):
    dir_end, iter_dir = read_directory(data)
    data = data[dir_end:]
    for line in iter_dir:
        yield (line[:3], get_tag_line(data, line))


@deprecated
def get_first_tag(data, want):  # return first line of wanted tag
    dir_end, iter_dir = read_directory(data)
    data = data[dir_end:]
    for line in iter_dir:
        if line[:3] in want:
            return get_tag_line(data, line)


re_dates = re.compile(r'^\(?(\d+-\d*|\d*-\d+)\)?$')


@deprecated
def get_person_content(line, is_marc8=False):
    contents = {}
    for k, v in get_subfields(line, ['a', 'b', 'c', 'd', 'q'], is_marc8):
        if k != 'd' and re_dates.match(v):  # wrong subtag
            k = 'd'
        contents.setdefault(k, []).append(v)
    return contents


@deprecated
def get_contents(line, want, is_marc8=False):
    contents = {}
    for k, v in get_subfields(line, want, is_marc8):
        contents.setdefault(k, []).append(v)
    return contents


@deprecated
def get_subfield_values(line, want, is_marc8=False):
    return [v for k, v in get_subfields(line, want, is_marc8)]


@deprecated
def read_control_number(line, is_marc8=False):
    assert line[-1] == '\x1e'
    return [line[:-1]]


@deprecated('Use catalog.marc.parse.read_isbn() instead.')
def read_isbn(line, is_marc8=False):
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


@deprecated
def read_publisher(line, is_marc8=False):
    return [
        i
        for i in (v.strip(' /,;:') for k, v in get_subfields(line, ['b'], is_marc8))
        if i
    ]


@deprecated
def read_author_org(line, is_marc8=False):
    name = " ".join(
        v.strip(' /,;:') for k, v in get_subfields(line, ['a', 'b'], is_marc8)
    )
    return [
        {
            'name': name,
            'db_name': name,
        }
    ]


@deprecated
def read_author_event(line, is_marc8=False):
    name = " ".join(
        v.strip(' /,;:') for k, v in get_subfields(line, ['a', 'b', 'd', 'n'], is_marc8)
    )
    return [
        {
            'name': name,
            'db_name': name,
        }
    ]


@deprecated('Use catalog.marc.marc_binary.handle_wrapped_lines() instead.')
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
            yield cur_tag, cur_lines[0][:-3] + ''.join(
                i[2:-3] for i in cur_lines[1:]
            ) + l[2:]
            cur_tag = None
            cur_lines = []
            continue
        yield t, l
    assert not cur_lines


@deprecated('Use catalog.marc.parse instead.')
def split_line(s):
    pos = -1
    marks = []
    while True:
        pos = s.find(b'\x1f', pos + 1)
        if pos == -1:
            break
        if s[pos + 1] != b'\x1b'[0]:
            marks.append(pos)
    if not marks:
        return [('v', s)]

    ret = []
    if s[: marks[0]]:
        ret.append(('v', s[: marks[0]]))
    for i in range(len(marks)):
        m = marks[i]
        ret.append(('k', s[m + 1 : m + 2]))
        if len(marks) == i + 1:
            if s[m + 2 :]:
                ret.append(('v', s[m + 2 :]))
        else:
            if s[m + 2 : marks[i + 1]]:
                ret.append(('v', s[m + 2 : marks[i + 1]]))
    return ret
