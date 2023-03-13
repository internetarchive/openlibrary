from pymarc import MARC8ToUnicode
from unicodedata import normalize

from openlibrary.catalog.marc import mnemonics
from openlibrary.catalog.marc.marc_base import MarcBase, MarcException, BadMARC


marc8 = MARC8ToUnicode(quiet=True)


class BadLength(MarcException):
    pass


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
        if len(l) > 500 and l.endswith(b'++\x1e'):
            assert not cur_tag or cur_tag == t
            cur_tag = t
            cur_lines.append(l)
            continue
        if cur_lines:
            yield cur_tag, cur_lines[0][:-3] + b''.join(
                i[2:-3] for i in cur_lines[1:]
            ) + l[2:]
            cur_tag = None
            cur_lines = []
            continue
        yield t, l
    assert not cur_lines


class BinaryDataField:
    def __init__(self, rec, line):
        """
        :param rec MarcBinary:
        :param line bytes: Content of a MARC21 binary field
        """
        self.rec = rec
        if line:
            while line[-2] == b'\x1e'[0]:  # ia:engineercorpsofhe00sher
                line = line[:-1]
        self.line = line

    def translate(self, data):
        """
        :param data bytes: raw MARC21 field data content, in either utf8 or marc8 encoding
        :rtype: str
        :return: A NFC normalized unicode str
        """
        if self.rec.marc8():
            data = mnemonics.read(data)
            return marc8.translate(data)
        return normalize('NFC', data.decode('utf8'))

    def ind1(self):
        return self.line[0]

    def ind2(self):
        return self.line[1]

    def remove_brackets(self):
        # TODO: remove this from MARCBinary,
        # stripping of characters should be done
        # from strings in openlibrary.catalog.marc.parse
        # not on the raw binary structure.
        # The intent is to remove initial and final square brackets
        # from field content. Try str.strip('[]')
        line = self.line
        if line[4] == b'['[0] and line[-2] == b']'[0]:
            last = line[-1]
            last_byte = bytes([last]) if isinstance(last, int) else last
            self.line = b''.join([line[0:4], line[5:-2], last_byte])

    def get_subfields(self, want):
        """
        :rtype: collections.Iterable[tuple]
        """
        want = set(want)
        for i in self.line[3:-1].split(b'\x1f'):
            code = i and (chr(i[0]) if isinstance(i[0], int) else i[0])
            if i and code in want:
                yield code, self.translate(i[1:])

    def get_contents(self, want):
        contents = {}
        for k, v in self.get_subfields(want):
            if v:
                contents.setdefault(k, []).append(v)
        return contents

    def get_subfield_values(self, want):
        """
        :rtype: list[str]
        """
        return [v for k, v in self.get_subfields(want)]

    def get_all_subfields(self):
        for i in self.line[3:-1].split(b'\x1f'):
            if i:
                j = self.translate(i)
                yield j[0], j[1:]

    def get_lower_subfield_values(self):
        for k, v in self.get_all_subfields():
            if k.islower():
                yield v


class MarcBinary(MarcBase):
    def __init__(self, data):
        # def __init__(self, data: bytes) -> None:  # Python 3 type hint
        try:
            assert len(data)
            assert isinstance(data, bytes)
            length = int(data[:5])
        except Exception:
            raise BadMARC("No MARC data found")
        if len(data) != length:
            raise BadLength(
                f"Record length {len(data)} does not match reported length {length}."
            )
        self.data = data
        self.directory_end = data.find(b'\x1e')
        if self.directory_end == -1:
            raise BadMARC("MARC directory not found")

    def iter_directory(self):
        data = self.data
        directory = data[24 : self.directory_end]
        if len(directory) % 12 != 0:
            # directory is the wrong size
            # sometimes the leader includes some utf-8 by mistake
            directory = data[: self.directory_end].decode('utf-8')[24:]
            if len(directory) % 12 != 0:
                raise BadMARC("MARC directory invalid length")
        iter_dir = (
            directory[i * 12 : (i + 1) * 12] for i in range(len(directory) // 12)
        )
        return iter_dir

    def leader(self):
        """
        :rtype: str
        """
        return self.data[:24].decode('utf-8', errors='replace')

    def marc8(self):
        """
        Is this binary MARC21 MARC8 encoded? (utf-8 if False)

        :rtype: bool
        """
        return self.leader()[9] == ' '

    def all_fields(self):
        return self.read_fields()

    def read_fields(self, want=None):
        """
        :param want list | None: list of str, 3 digit MARC field ids, or None for all fields (no limit)
        :rtype: generator
        :return: Generator of (tag (str), field (str if 00x, otherwise BinaryDataField))
        """
        if want is None:
            fields = self.get_all_tag_lines()
        else:
            fields = self.get_tag_lines(want)

        for tag, line in handle_wrapped_lines(fields):
            if want and tag not in want:
                continue
            if tag.startswith('00'):
                # marc_upei/marc-for-openlibrary-bigset.mrc:78997353:588
                if tag == '008' and line == b'':
                    continue
                assert line[-1] == b'\x1e'[0]
                # Tag contents should be strings in utf-8 by this point
                # if not, the MARC is corrupt in some way. Attempt to rescue
                # using 'replace' error handling. We don't want to change offsets
                # in positionaly defined control fields like 008
                yield tag, line[:-1].decode('utf-8', errors='replace')
            else:
                yield tag, BinaryDataField(self, line)

    def get_all_tag_lines(self):
        for line in self.iter_directory():
            yield (line[:3].decode(), self.get_tag_line(line))

    def get_tag_lines(self, want):
        """
        Returns a list of selected fields, (tag, field contents)

        :param want list: List of str, 3 digit MARC field ids
        :rtype: list
        :return: list of tuples (MARC tag (str), field contents ... bytes or str?)
        """
        want = set(want)
        return [
            (line[:3].decode(), self.get_tag_line(line))
            for line in self.iter_directory()
            if line[:3].decode() in want
        ]

    def get_tag_line(self, line):
        length = int(line[3:7])
        offset = int(line[7:12])
        data = self.data[self.directory_end :]
        # handle off-by-one errors in MARC records
        try:
            if data[offset] != b'\x1e':
                offset += data[offset:].find(b'\x1e')
            last = offset + length
            if data[last] != b'\x1e':
                length += data[last:].find(b'\x1e')
        except IndexError:
            pass
        tag_line = data[offset + 1 : offset + length + 1]
        if line[0:2] != '00':
            # marc_western_washington_univ/wwu_bibs.mrc_revrev.mrc:636441290:1277
            if tag_line[1:8] == b'{llig}\x1f':
                tag_line = tag_line[0] + '\uFE20' + tag_line[7:]
        return tag_line

    def decode_field(self, field):
        # noop on MARC binary
        return field
