from pymarc import MARC8ToUnicode
from unicodedata import normalize

from openlibrary.catalog.marc import mnemonics
from openlibrary.catalog.marc.marc_base import MarcBase, MarcException, BadMARC


import six


marc8 = MARC8ToUnicode(quiet=True)


class BadLength(MarcException):
    pass


def norm(s):
    return normalize('NFC', six.text_type(s))


def handle_wrapped_lines(_iter):
    """ 
    Handles wrapped MARC fields, which appear to be multiple
    fields with the same field number ending with ++
    Have not found an official spec which describe this.
    """
    cur_lines = []
    cur_tag = None
    maybe_wrap = False
    for t, l in _iter:
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


class BinaryDataField():
    def __init__(self, rec, line):
        self.rec = rec
        if line:
            while line[-2] == '\x1e': # ia:engineercorpsofhe00sher
                line = line[:-1]
        self.line = line

    def translate(self, data):
        utf8 = self.rec.leader()[9] == 'a'
        if utf8:
            try:
                data = data.decode('utf-8')
            except:
                utf8 = False
        if not utf8:
            data = mnemonics.read(data)
            data = marc8.translate(data)
        data = normalize('NFC', data)
        return data

    def ind1(self):
        return self.line[0]

    def ind2(self):
        return self.line[1]

    def remove_brackets(self):
        line = self.line
        if line[4] == '[' and line[-2] == ']':
            self.line = line[0:4] + line[5:-2] + line[-1]

    def get_subfields(self, want):
        want = set(want)
        for i in self.line[3:-1].split('\x1f'):
            if i and i[0] in want:
                yield i[0], self.translate(i[1:])

    def get_contents(self, want):
        contents = {}
        for k, v in self.get_subfields(want):
            if v:
                contents.setdefault(k, []).append(v)
        return contents

    def get_subfield_values(self, want):
        return [v for k, v in self.get_subfields(want)]

    def get_all_subfields(self):
        for i in self.line[3:-1].split('\x1f'):
            if i:
                j = self.translate(i)
                yield j[0], j[1:]

    def get_lower_subfields(self):
        for k, v in self.get_all_subfields():
            if k.islower():
                yield v


class MarcBinary(MarcBase):
    def __init__(self, data):
        try:
            assert len(data) and isinstance(data, six.string_types)
            length = int(data[:5])
        except:
            raise BadMARC("No MARC data found")
        if len(data) != length:
            raise BadLength("Record length %s does not match reported length %s." % (len(data), length))
        self.data = data
        self.directory_end = data.find('\x1e')
        if self.directory_end == -1:
            raise BadMARC("MARC directory not found")

    def iter_directory(self):
        data = self.data
        directory = data[24:self.directory_end]
        if len(directory) % 12 != 0:
            # directory is the wrong size
            # sometimes the leader includes some utf-8 by mistake
            directory = data[:self.directory_end].decode('utf-8')[24:]
            if len(directory) % 12 != 0:
                raise BadMARC("MARC directory invalid length")
        iter_dir = (directory[i*12:(i+1)*12] for i in range(len(directory) / 12))
        return iter_dir

    def leader(self):
        return self.data[:24]

    def all_fields(self):
        marc8 = self.leader()[9] != 'a'
        for tag, line in handle_wrapped_lines(self.get_all_tag_lines()):
            if tag.startswith('00'):
                # marc_upei/marc-for-openlibrary-bigset.mrc:78997353:588
                if tag == '008' and line == '':
                    continue
                assert line[-1] == '\x1e'
                yield tag, line[:-1]
            else:
                yield tag, BinaryDataField(self, line)

    def read_fields(self, want):
        want = set(want)
        marc8 = self.leader()[9] != 'a'
        for tag, line in handle_wrapped_lines(self.get_tag_lines(want)):
            if tag not in want:
                continue
            if tag.startswith('00'):
                # marc_upei/marc-for-openlibrary-bigset.mrc:78997353:588
                if tag == '008' and line == '':
                    continue
                assert line[-1] == '\x1e'
                yield tag, line[:-1]
            else:
                yield tag, BinaryDataField(self, line)

    def get_all_tag_lines(self):
        for line in self.iter_directory():
            yield (line[:3], self.get_tag_line(line))

    def get_tag_lines(self, want):
        want = set(want)
        return [(line[:3], self.get_tag_line(line)) for line in self.iter_directory() if line[:3] in want]

    def get_tag_line(self, line):
        length = int(line[3:7])
        offset = int(line[7:12])
        data = self.data[self.directory_end:]
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

    def decode_field(self, field):
        return field  # noop on MARC binary

    def read_isbn(self, f):
        if '\x1f' in f.line:
            return super(MarcBinary, self).read_isbn(f)
        else:
            m = re_isbn.match(f.line[3:-1])
            if m:
                return [m.group(1)]
        return []
