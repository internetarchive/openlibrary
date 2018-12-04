from openlibrary.catalog.marc import fast_parse
#TODO: Move fast_parse get_tag_lines(), handle_wrapped_lines(), get_all_tag_lines() into this class
from marc_base import MarcBase, MarcException, BadMARC
from unicodedata import normalize
from pymarc import MARC8ToUnicode
from openlibrary.catalog.marc import mnemonics

import six


marc8 = MARC8ToUnicode(quiet=True)

class BadLength(MarcException):
    pass

def norm(s):
    return normalize('NFC', unicode(s))

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
        return fast_parse.get_all_subfields(self.line, self.rec.leader()[9] != 'a')

    def get_all_subfields(self):
        for i in self.line[3:-1].split('\x1f'):
            if i:
                j = self.translate(i)
                yield j[0], j[1:]

    def get_lower_subfields(self):
        for k, v in self.get_all_subfields():
            if k.islower():
                yield v

#class BinaryIaDataField(BinaryDataField):
#    def translate(self, data):
#        return fast_parse.translate(data, bad_ia_charset=True)

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

    def leader(self):
        return self.data[:24]

    def all_fields(self):
        marc8 = self.leader()[9] != 'a'
        for tag, line in fast_parse.handle_wrapped_lines(fast_parse.get_all_tag_lines(self.data)):
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
        for tag, line in fast_parse.handle_wrapped_lines(fast_parse.get_tag_lines(self.data, want)):
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

    def decode_field(self, field):
        return field # noop on MARC binary

    def read_isbn(self, f):
        if '\x1f' in f.line:
            return super(MarcBinary, self).read_isbn(f)
        else:
            m = re_isbn.match(f.line[3:-1])
            if m:
                return [m.group(1)]
        return []
